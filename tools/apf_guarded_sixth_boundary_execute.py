#!/usr/bin/env python3
"""Execute APF through exactly its sixth typed boundary in isolation."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

import apf_guarded_first_entry_execute as first
import apf_guarded_fifth_boundary_execute as fifth


SCHEMA = "apf2k8_guarded_sixth_boundary_execution/v1"
RESULT_PREFIX = "APF_GUARDED_SIXTH_BOUNDARY_CHILD_RESULT "
EXPECTED_XEX_SHA256 = fifth.EXPECTED_XEX_SHA256
EXPECTED_VOLUME_SHA256 = fifth.EXPECTED_VOLUME_SHA256
EXPECTED_DECODED_SHA256 = fifth.EXPECTED_DECODED_SHA256
EXPECTED_DECODED_SIZE = fifth.EXPECTED_DECODED_SIZE
EXPECTED_COMPOSED_REPORT_SHA256 = fifth.EXPECTED_COMPOSED_REPORT_SHA256
EXPECTED_BUDGET_REPORT_SHA256 = fifth.EXPECTED_BUDGET_REPORT_SHA256
EXPECTED_COMPOSED_TREE_SHA256 = fifth.EXPECTED_COMPOSED_TREE_SHA256
EXPECTED_INSTRUMENTED_TREE_SHA256 = fifth.EXPECTED_INSTRUMENTED_TREE_SHA256
EXPECTED_HOOK_MANIFEST_SHA256 = fifth.EXPECTED_HOOK_MANIFEST_SHA256
EXPECTED_NUMBERED_COUNT = fifth.EXPECTED_NUMBERED_COUNT
EXPECTED_MAPPING_COUNT = fifth.EXPECTED_MAPPING_COUNT
EXPECTED_HOOK_COUNT = fifth.EXPECTED_HOOK_COUNT
EXPECTED_IMPORT_COUNT = fifth.EXPECTED_IMPORT_COUNT
EXPECTED_TYPED_IMPORT_COUNT = fifth.EXPECTED_TYPED_IMPORT_COUNT
EXPECTED_ENTRY = fifth.EXPECTED_ENTRY
EXPECTED_FIRST_BRIDGE_SHA256 = fifth.EXPECTED_FIRST_BRIDGE_SHA256
EXPECTED_BUDGET_SOURCE_SHA256 = fifth.EXPECTED_BUDGET_SOURCE_SHA256
EXPECTED_LEAF_REPORT_SHA256 = fifth.EXPECTED_LEAF_REPORT_SHA256
EXPECTED_FIFTH_DRIVER_SHA256 = (
    "254e71ccd95b2f1140129b2edc5961d3be25afb1cda6b256ad1e988993e149d0"
)
EXPECTED_FIFTH_REPORT_SHA256 = (
    "d12897cd8c5575c1f770a7f5429f02777c1028574014fb7e59def40dade9478d"
)
EXPECTED_POST_CRITICAL_STATIC_SHA256 = (
    "861ae4847338e5d2fa46a5b6d536754511b3afe25435ffd9817e43cf2d805a0a"
)
EXPECTED_POST_CRITICAL_ANALYZER_SHA256 = (
    "451e1959603390bd59cfca43c43141b4233709a8886a78c4e171a169139b7fe9"
)
EXPECTED_SIXTH_CALL = 0x84BF0C6C
EXPECTED_SIXTH_RETURN = 0x84BF0C70
EXPECTED_SIXTH_THUNK = 0x84D07FCC
EXPECTED_SIXTH_ARGUMENT = 0x84F02424
EXPECTED_CURRENT_THREAD = 0x70020200
EXPECTED_CONTINUATION_INSTRUCTIONS = 314
EXPECTED_CUMULATIVE_INSTRUCTIONS = 1333
EXPECTED_CONTINUATION_TRACE_SHA256 = (
    "f69b0d8c265278630f99d102cb7107c1db80f983beefc1f247b2c761d3f428d1"
)
EXPECTED_PRE_SIXTH_BACKING_FNV = 0x182C7A2CE1705280
EXPECTED_POST_SIXTH_BACKING_FNV = 0x182C7A2CE1705280
INSTRUCTION_LIMIT = 4096
FUNCTION_DISPATCH_LIMIT = 64
AUTHORIZATION_TOKEN = (
    "apf2k8-v1:d12897cd:861ae484:981a5714:cde5b922:"
    "sixth-boundary-global-critical-enter-only"
)
AUTHORIZATION_NONCE = 0xA2F2606C0C6C0C70


class SixthBoundaryError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SixthBoundaryError(message)


def sha256_file(path: Path) -> str:
    return first.sha256_file(path)


def pin(path: Path, root: Path) -> dict[str, Any]:
    return first.pin(path, root)


def trace_sha256(trace: list[int]) -> str:
    return hashlib.sha256("".join(
        f"0x{pc:08X}\n" for pc in trace).encode("ascii")).hexdigest()


def evidence_header_source() -> str:
    source = fifth.evidence_header_source()
    source = source.replace("vc_apf_fifth_boundary_",
                            "vc_apf_sixth_boundary_")
    marker = "    std::uint64_t fifth_backing_fnv_after_adapter;\n};"
    require(source.count(marker) == 1, "fifth evidence tail changed")
    return source.replace(marker, r'''    std::uint64_t fifth_backing_fnv_after_adapter;
    std::uint32_t sixth_thunk;
    std::uint32_t sixth_lr;
    std::uint32_t sixth_r3_input;
    std::uint32_t sixth_r3_output;
    std::uint32_t sixth_instruction_count;
    std::uint32_t sixth_vm_ledger_exact_before_adapter;
    std::uint32_t sixth_backing_exact_before_adapter;
    std::uint64_t sixth_backing_fnv_before_adapter;
    std::uint32_t sixth_critical_section_exact_before_adapter;
    std::uint32_t sixth_critical_section_exact_after_adapter;
    std::uint32_t sixth_lock_count_after_adapter;
    std::uint32_t sixth_recursion_count_after_adapter;
    std::uint32_t sixth_owner_after_adapter;
    std::uint64_t sixth_backing_fnv_after_adapter;
};''')


def specialized_budget_source(original: str) -> str:
    source = fifth.specialized_budget_source(original)
    return source.replace("vc_apf_fifth_boundary_full_",
                          "vc_apf_sixth_boundary_full_")


def specialized_bridge_source(original: str) -> str:
    source = fifth.specialized_bridge_source(original)
    for old, new in (
        ('#include "fifth_boundary_evidence.h"',
         '#include "sixth_boundary_evidence.h"'),
        ("vc_apf_fifth_boundary_", "vc_apf_sixth_boundary_"),
        ("UINT64_C(0xA2F25009D9549585)",
         "UINT64_C(0xA2F2606C0C6C0C70)"),
    ):
        source = source.replace(old, new)

    dispatch_marker = "void dispatch_and_stop(PPCContext &context, std::uint8_t *base,\n"
    require(source.count(dispatch_marker) == 1,
            "sixth bridge dispatch marker changed")
    helpers = r'''bool overlap_vm_ledger_exact(
    const vc_apf_first_entry_state &state, bool second_page_committed) {
    const vc_apf_boot_leaf_runtime &runtime = *state.adapter_runtime;
    if (runtime.vm_page_count != 4096u ||
        runtime.vm_allocation_count != 1u ||
        !runtime.vm_allocations[0].active ||
        runtime.vm_allocations[0].base_page != 0u ||
        runtime.vm_allocations[0].page_count != 16u ||
        runtime.vm_allocations[0].allocation_protect !=
            VC_APF_X_PAGE_READWRITE) return false;
    for (std::size_t index = 1u;
         index < VC_APF_BOOT_VM_MAX_ALLOCATIONS; ++index) {
        if (runtime.vm_allocations[index].active) return false;
    }
    for (std::size_t index = 0u; index < runtime.vm_page_count; ++index) {
        const vc_apf_boot_vm_page &page = runtime.vm_pages[index];
        if (index < 16u) {
            const std::uint8_t expected_state =
                index == 0u || (second_page_committed && index == 1u)
                    ? 2u : 1u;
            if (page.allocation_id != 1u || page.state != expected_state ||
                page.protect != VC_APF_X_PAGE_READWRITE) return false;
        } else if (page.allocation_id != 0u || page.state != 0u ||
                   page.protect != 0u) return false;
    }
    return true;
}

bool post_fifth_backing_exact(
    const vc_apf_first_entry_state &state, bool second_page_committed) {
    const std::uint8_t *const bytes =
        state.adapter_runtime->config.vm_backing_bytes;
    std::size_t nonzero = 0u;
    for (std::size_t index = 0u; index < 0x00010000u; ++index) {
        if (bytes[index] != 0u) ++nonzero;
    }
    if (nonzero != 814u || load_bridge_be_u16(bytes) != 0x0063u ||
        bytes[5] != 1u || load_bridge_be_u32(bytes + 16u) != 0xEEFFEEFFu ||
        load_bridge_be_u32(bytes + 20u) != 2u ||
        load_bridge_be_u32(bytes + 24u) != 0u ||
        load_bridge_be_u16(bytes + 58u) != 0x0610u ||
        load_bridge_be_u32(bytes + 60u) != 0u ||
        load_bridge_be_u32(bytes + 76u) != 0x40000590u ||
        load_bridge_be_u32(bytes + 88u) != 0x40000058u ||
        load_bridge_be_u32(bytes + 92u) != 0x40000058u ||
        load_bridge_be_u16(bytes + 368u) != 0xFFFFu || bytes[379] != 1u ||
        load_bridge_be_u32(bytes + 0x580u) != 0x40000610u ||
        load_bridge_be_u32(bytes + 0x600u) != 0u ||
        load_bridge_be_u32(bytes + 0x610u) != 0x01000400u ||
        load_bridge_be_u32(bytes + 0x614u) != 0u ||
        load_bridge_be_u32(bytes + 0x618u) != 0x40000618u ||
        load_bridge_be_u32(bytes + 0x61Cu) != 0x40000618u ||
        load_bridge_be_u32(bytes + 0x620u) != 0xFFFFFFFFu ||
        load_bridge_be_u32(bytes + 0x624u) != 0u ||
        load_bridge_be_u32(bytes + 0x628u) != 0u) return false;
    for (std::size_t index = 0u; index < 128u; ++index) {
        const std::size_t offset = 384u + index * 8u;
        if (load_bridge_be_u32(bytes + offset) != 0x40000000u + offset ||
            load_bridge_be_u32(bytes + offset + 4u) !=
                0x40000000u + offset) return false;
    }
    for (std::size_t index = 0u; index < 7u; ++index) {
        const std::size_t offset = 0x590u + index * 0x10u;
        if (load_bridge_be_u32(bytes + offset) !=
            0x40000000u + offset + 0x10u) return false;
    }
    for (std::size_t index = 0x00010000u;
         index < 0x00100000u; ++index) {
        const std::uint8_t expected =
            second_page_committed && index < 0x00020000u
                ? 0u
                : static_cast<std::uint8_t>((index * 131u + 17u) & 0xFFu);
        if (bytes[index] != expected) return false;
    }
    return true;
}

bool normalize_overlap_commit_backing(vc_apf_first_entry_state &state) {
    std::uint8_t *const bytes = state.adapter_runtime->config.vm_backing_bytes;
    bool zero = true;
    bool pattern = true;
    for (std::size_t index = 0x00010000u; index < 0x00020000u; ++index) {
        if (bytes[index] != 0u) zero = false;
        if (bytes[index] != static_cast<std::uint8_t>(
                (index * 131u + 17u) & 0xFFu)) pattern = false;
    }
    if (!zero && !pattern) return false;
    if (pattern) std::memset(bytes + 0x00010000u, 0, 0x00010000u);
    return true;
}

bool post_allocator_backing_shape_exact(
    const vc_apf_first_entry_state &state) {
    const std::uint8_t *const bytes =
        state.adapter_runtime->config.vm_backing_bytes;
    if (load_bridge_be_u16(bytes) != 0x0063u || bytes[5] != 1u ||
        load_bridge_be_u32(bytes + 16u) != 0xEEFFEEFFu ||
        load_bridge_be_u32(bytes + 20u) != 2u ||
        load_bridge_be_u16(bytes + 58u) != 0x0610u ||
        load_bridge_be_u32(bytes + 76u) != 0x40000590u ||
        load_bridge_be_u32(bytes + 0x580u) != 0x40000610u ||
        load_bridge_be_u32(bytes + 0x610u) != 0x01000400u ||
        load_bridge_be_u32(bytes + 0x618u) != 0x40000618u ||
        load_bridge_be_u32(bytes + 0x61Cu) != 0x40000618u ||
        load_bridge_be_u32(bytes + 0x620u) != 0xFFFFFFFFu ||
        load_bridge_be_u32(bytes + 0x624u) != 0u ||
        load_bridge_be_u32(bytes + 0x628u) != 0u) return false;
    for (std::size_t index = 0x00010000u;
         index < 0x00100000u; ++index) {
        if (bytes[index] != static_cast<std::uint8_t>(
                (index * 131u + 17u) & 0xFFu)) return false;
    }
    return true;
}

bool global_critical_section_exact(std::uint8_t *base, bool acquired) {
    const std::uint8_t *const bytes = base + 0x84F02424u;
    return load_bridge_be_u32(bytes) == 0x01000400u &&
           load_bridge_be_u32(bytes + 4u) == 0u &&
           load_bridge_be_u32(bytes + 8u) == 0x84F0242Cu &&
           load_bridge_be_u32(bytes + 12u) == 0x84F0242Cu &&
           load_bridge_be_u32(bytes + 16u) ==
               (acquired ? 0u : 0xFFFFFFFFu) &&
           load_bridge_be_u32(bytes + 20u) == (acquired ? 1u : 0u) &&
           load_bridge_be_u32(bytes + 24u) ==
               (acquired ? 0x70020200u : 0u);
}

'''
    source = source.replace(dispatch_marker, helpers + dispatch_marker, 1)

    old_fifth_tail = r'''        vc_apf_sixth_boundary_observed.stage = 5u;
        /* Throw unconditionally: 0x84BED958 must not execute. */
        stop(gate_status, adapter_status);
    }
'''
    new_fifth_tail = r'''        if (gate_status != VC_APF_FIRST_ENTRY_OK ||
            adapter_status != VC_APF_BOOT_LEAF_OK ||
            adapter_context.gpr[3] != UINT64_C(0x40000610) ||
            vc_apf_bound_state->budget.function_dispatches_consumed != 5u ||
            !committed_vm_ledger_exact(*vc_apf_bound_state) ||
            !post_process_type_backing_exact(*vc_apf_bound_state, true) ||
            reserve_backing_fnv(*vc_apf_bound_state) !=
                UINT64_C(0xD0D16B728ECA1764)) {
            stop(gate_status, adapter_status);
        }
        vc_apf_sixth_boundary_observed.stage = 5u;
        return;
    }
'''
    require(source.count(old_fifth_tail) == 1,
            "fifth terminal dispatch changed")
    source = source.replace(old_fifth_tail, new_fifth_tail, 1)

    stage_two_marker = (
        "    if (vc_apf_sixth_boundary_observed.stage != 2u ||\n"
        "        import_thunk != VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY ||\n"
    )
    require(source.count(stage_two_marker) == 1,
            "sixth insertion marker changed")
    sixth_dispatch = r'''    if (vc_apf_sixth_boundary_observed.stage == 5u) {
        const bool vm_exact = overlap_vm_ledger_exact(
            *vc_apf_bound_state, false);
        const bool backing_exact = post_fifth_backing_exact(
            *vc_apf_bound_state, false);
        const std::uint64_t backing_fnv = reserve_backing_fnv(
            *vc_apf_bound_state);
        const std::uint32_t base_before =
            load_bridge_be_u32(base + 0x7001FC3Cu);
        const std::uint32_t size_before =
            load_bridge_be_u32(base + 0x7001FBA0u);
        if (import_thunk != VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY ||
            adapter_context.lr != 0x84BECE18u ||
            adapter_context.gpr[3] != UINT64_C(0x7001FC3C) ||
            adapter_context.gpr[4] != UINT64_C(0x7001FBA0) ||
            adapter_context.gpr[5] != UINT64_C(0x60001000) ||
            adapter_context.gpr[6] != UINT64_C(0x00000004) ||
            adapter_context.gpr[7] != 0u ||
            base_before != 0x40000000u || size_before != 0x00010060u ||
            vc_apf_bound_state->budget.function_dispatches_consumed != 5u ||
            vc_apf_guest_instruction_budget_snapshot(&trace) !=
                VC_APF_FIRST_ENTRY_OK ||
            trace.successful_instruction_count != 1079u ||
            trace.recent_count == 0u ||
            trace.recent_addresses[trace.recent_count - 1u] !=
                0x84BECE14u || !vm_exact || !backing_exact ||
            backing_fnv != UINT64_C(0xA2F6E3132B6EE02A)) {
            stop(VC_APF_FIRST_ENTRY_NOT_AUTHORIZED,
                 VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
        }
        vc_apf_sixth_boundary_observed.sixth_thunk = import_thunk;
        vc_apf_sixth_boundary_observed.sixth_lr = adapter_context.lr;
        vc_apf_sixth_boundary_observed.sixth_r3_input =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        vc_apf_sixth_boundary_observed.sixth_r4_input =
            static_cast<std::uint32_t>(adapter_context.gpr[4]);
        vc_apf_sixth_boundary_observed.sixth_r5_input =
            static_cast<std::uint32_t>(adapter_context.gpr[5]);
        vc_apf_sixth_boundary_observed.sixth_r6_input =
            static_cast<std::uint32_t>(adapter_context.gpr[6]);
        vc_apf_sixth_boundary_observed.sixth_r7_input =
            static_cast<std::uint32_t>(adapter_context.gpr[7]);
        vc_apf_sixth_boundary_observed.sixth_base_before = base_before;
        vc_apf_sixth_boundary_observed.sixth_size_before = size_before;
        vc_apf_sixth_boundary_observed.sixth_instruction_count =
            static_cast<std::uint32_t>(trace.successful_instruction_count);
        vc_apf_sixth_boundary_observed
            .sixth_vm_ledger_exact_before_adapter = vm_exact ? 1u : 0u;
        vc_apf_sixth_boundary_observed.sixth_backing_exact_before_adapter =
            backing_exact ? 1u : 0u;
        vc_apf_sixth_boundary_observed.sixth_backing_fnv_before_adapter =
            backing_fnv;
        gate_status = vc_apf_first_entry_dispatch_import(
            vc_apf_bound_state, &adapter_context, import_thunk,
            &adapter_status);
        for (index = 0u; index < 32u; ++index) {
            write_gpr(context, index, adapter_context.gpr[index]);
        }
        context.lr = adapter_context.lr;
        const bool normalized =
            gate_status == VC_APF_FIRST_ENTRY_OK &&
            adapter_status == VC_APF_BOOT_LEAF_OK &&
            adapter_context.gpr[3] == VC_APF_X_STATUS_SUCCESS &&
            load_bridge_be_u32(base + 0x7001FC3Cu) == 0x40000000u &&
            load_bridge_be_u32(base + 0x7001FBA0u) == 0x00020000u &&
            overlap_vm_ledger_exact(*vc_apf_bound_state, true) &&
            normalize_overlap_commit_backing(*vc_apf_bound_state);
        vc_apf_sixth_boundary_observed.sixth_r3_output =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        vc_apf_sixth_boundary_observed.sixth_base_after =
            load_bridge_be_u32(base + 0x7001FC3Cu);
        vc_apf_sixth_boundary_observed.sixth_size_after =
            load_bridge_be_u32(base + 0x7001FBA0u);
        vc_apf_sixth_boundary_observed.sixth_vm_ledger_exact_after_adapter =
            overlap_vm_ledger_exact(*vc_apf_bound_state, true) ? 1u : 0u;
        vc_apf_sixth_boundary_observed.sixth_backing_exact_after_adapter =
            post_fifth_backing_exact(*vc_apf_bound_state, true) ? 1u : 0u;
        vc_apf_sixth_boundary_observed.sixth_new_page_zeroed_after_adapter =
            normalized ? 1u : 0u;
        vc_apf_sixth_boundary_observed.sixth_backing_fnv_after_adapter =
            reserve_backing_fnv(*vc_apf_bound_state);
        vc_apf_sixth_boundary_observed.stage = 6u;
        /* Throw unconditionally: 0x84BECE18 must not execute. */
        stop(normalized ? gate_status : VC_APF_FIRST_ENTRY_NOT_AUTHORIZED,
             normalized ? adapter_status :
                          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    }

'''
    return source.replace(stage_two_marker,
                          sixth_dispatch + stage_two_marker, 1)


def harness_source() -> str:
    source = fifth.harness_source()
    for old, new in (
        ('#include "fifth_boundary_evidence.h"',
         '#include "sixth_boundary_evidence.h"'),
        ("vc_apf_fifth_boundary_", "vc_apf_sixth_boundary_"),
        ("APF_GUARDED_FIFTH_BOUNDARY_CHILD_RESULT",
         "APF_GUARDED_SIXTH_BOUNDARY_CHILD_RESULT"),
        ("expected_fifth_boundary", "expected_sixth_boundary"),
        ("apf2k8-v1:98403d88:1ad60880:981a5714:cde5b922:"
         "fifth-boundary-critical-section-only",
         "apf2k8-v1:d12897cd:138aebc8:981a5714:cde5b922:"
         "sixth-boundary-overlap-commit-only"),
        ("UINT64_C(0xA2F25009D9549585)",
         "UINT64_C(0xA2F26014CE14CE18)"),
        ("constexpr std::uint32_t kMagic = 0x41504636u;",
         "constexpr std::uint32_t kMagic = 0x41504637u;"),
    ):
        source = source.replace(old, new)

    constants = "constexpr std::uint32_t kExpectedFifthArgument = 0x40000610u;\n"
    require(source.count(constants) == 1, "sixth harness constants changed")
    source = source.replace(constants, constants + r'''constexpr std::uint32_t kExpectedSixthThunk = 0x84D0863Cu;
constexpr std::uint32_t kExpectedSixthCall = 0x84BECE14u;
constexpr std::uint32_t kExpectedSixthReturn = 0x84BECE18u;
constexpr std::uint32_t kExpectedSixthBasePointer = 0x7001FC3Cu;
constexpr std::uint32_t kExpectedSixthSizePointer = 0x7001FBA0u;
''', 1)

    helper_start = source.index("bool initialized_page_exact(")
    helper_end = source.index("\nstd::int64_t monotonic_milliseconds()", helper_start)
    helper = r'''bool initialized_page_exact(const std::uint8_t *bytes) {
    std::size_t nonzero = 0u;
    for (std::size_t index = 0u; index < 0x10000u; ++index) {
        if (bytes[index] != 0u) ++nonzero;
    }
    if (nonzero != 814u || load_be_u32(bytes + 16u) != 0xEEFFEEFFu ||
        load_be_u32(bytes + 20u) != 2u ||
        load_be_u32(bytes + 24u) != 0u ||
        load_be_u32(bytes + 60u) != 0u ||
        load_be_u32(bytes + 76u) != 0x40000590u ||
        load_be_u32(bytes + 88u) != 0x40000058u ||
        load_be_u32(bytes + 92u) != 0x40000058u || bytes[0] != 0u ||
        bytes[1] != 0x63u || bytes[5] != 1u || bytes[58] != 0x06u ||
        bytes[59] != 0x10u || bytes[368] != 0xFFu ||
        bytes[369] != 0xFFu || bytes[379] != 1u) return false;
    for (std::size_t index = 0u; index < 128u; ++index) {
        const std::size_t offset = 384u + index * 8u;
        if (load_be_u32(bytes + offset) != 0x40000000u + offset ||
            load_be_u32(bytes + offset + 4u) !=
                0x40000000u + offset) return false;
    }
    for (std::size_t index = 0u; index < 7u; ++index) {
        const std::size_t offset = 0x590u + index * 0x10u;
        if (load_be_u32(bytes + offset) !=
            0x40000000u + offset + 0x10u) return false;
    }
    return load_be_u32(bytes + 0x580u) == 0x40000610u &&
           load_be_u32(bytes + 0x600u) == 0u &&
           load_be_u32(bytes + 0x610u) == 0x01000400u &&
           load_be_u32(bytes + 0x614u) == 0u &&
           load_be_u32(bytes + 0x618u) == 0x40000618u &&
           load_be_u32(bytes + 0x61Cu) == 0x40000618u &&
           load_be_u32(bytes + 0x620u) == 0xFFFFFFFFu &&
           load_be_u32(bytes + 0x624u) == 0u &&
           load_be_u32(bytes + 0x628u) == 0u;
}
'''
    source = source[:helper_start] + helper + source[helper_end:]

    ledger_start = source.index("bool final_vm_ledger_exact(")
    ledger_end = source.index("\n[[noreturn]] void execute_child", ledger_start)
    ledger = r'''bool final_vm_ledger_exact(const vc_apf_boot_leaf_runtime &runtime,
                           std::uint32_t *reserved_count,
                           std::uint32_t *committed_count) {
    std::uint32_t reserved = 0u;
    std::uint32_t committed = 0u;
    if (runtime.vm_page_count != 4096u ||
        runtime.vm_allocation_count != 1u ||
        !runtime.vm_allocations[0].active ||
        runtime.vm_allocations[0].base_page != 0u ||
        runtime.vm_allocations[0].page_count != 16u ||
        runtime.vm_allocations[0].allocation_protect !=
            VC_APF_X_PAGE_READWRITE) return false;
    for (std::size_t index = 1u;
         index < VC_APF_BOOT_VM_MAX_ALLOCATIONS; ++index) {
        if (runtime.vm_allocations[index].active) return false;
    }
    for (std::size_t index = 0u; index < runtime.vm_page_count; ++index) {
        const vc_apf_boot_vm_page &page = runtime.vm_pages[index];
        if (index < 2u) {
            if (page.allocation_id != 1u || page.state != 2u ||
                page.protect != VC_APF_X_PAGE_READWRITE) return false;
            ++committed;
        } else if (index < 16u) {
            if (page.allocation_id != 1u || page.state != 1u ||
                page.protect != VC_APF_X_PAGE_READWRITE) return false;
            ++reserved;
        } else if (page.allocation_id != 0u || page.state != 0u ||
                   page.protect != 0u) return false;
    }
    *reserved_count = reserved;
    *committed_count = committed;
    return reserved == 14u && committed == 2u;
}
'''
    source = source[:ledger_start] + ledger + source[ledger_end:]

    old_pattern = r'''    report.remaining_backing_pattern_exact = 1u;
    for (std::uint32_t index = kCommitSize;
         index < kRequestedSize; ++index) {
        if (vm_backing[index] != static_cast<std::uint8_t>(
                (index * 131u + 17u) & 0xFFu)) {
            report.remaining_backing_pattern_exact = 0u;
            break;
        }
    }'''
    new_pattern = r'''    report.remaining_backing_pattern_exact = 1u;
    for (std::uint32_t index = 0x00010000u;
         index < 0x00020000u; ++index) {
        if (vm_backing[index] != 0u) {
            report.remaining_backing_pattern_exact = 0u;
            break;
        }
    }
    if (report.remaining_backing_pattern_exact != 0u) {
        for (std::uint32_t index = 0x00020000u;
             index < kRequestedSize; ++index) {
            if (vm_backing[index] != static_cast<std::uint8_t>(
                    (index * 131u + 17u) & 0xFFu)) {
                report.remaining_backing_pattern_exact = 0u;
                break;
            }
        }
    }'''
    require(source.count(old_pattern) == 1,
            "sixth harness backing check changed")
    source = source.replace(old_pattern, new_pattern, 1)

    catch_old = (
        "report.outcome = stop.import_thunk == kExpectedFifthThunk\n"
        "                             ? child_outcome::expected_sixth_boundary\n"
    )
    catch_new = (
        "report.outcome = stop.import_thunk == kExpectedSixthThunk\n"
        "                             ? child_outcome::expected_sixth_boundary\n"
    )
    require(source.count(catch_old) == 1, "sixth harness catch gate changed")
    source = source.replace(catch_old, catch_new, 1)

    expected_start = source.index("    const bool expected =\n")
    expected_end = source.index(
        "\n    vc_apf_guest_instruction_budget_unbind();", expected_start)
    expected = r'''    const bool expected =
        report.outcome == child_outcome::expected_sixth_boundary &&
        report.gate_status == VC_APF_FIRST_ENTRY_OK &&
        report.adapter_status == VC_APF_BOOT_LEAF_OK &&
        report.import_thunk == kExpectedSixthThunk &&
        report.instructions_consumed == 1079u &&
        report.function_dispatches_consumed == 6u &&
        report.trace_count == 1079u &&
        report.last_guest_address == kExpectedSixthCall &&
        report.context_lr == kExpectedSixthReturn &&
        report.context_r3 == VC_APF_X_STATUS_SUCCESS &&
        report.bridge.stage == 6u &&
        report.bridge.first_instruction_count == 38u &&
        report.bridge.second_instruction_count == 264u &&
        report.bridge.third_instruction_count == 283u &&
        report.bridge.fourth_instruction_count == 365u &&
        report.bridge.fifth_instruction_count == 1019u &&
        report.bridge.fifth_thunk == kExpectedFifthThunk &&
        report.bridge.fifth_lr == kExpectedFifthReturn &&
        report.bridge.fifth_critical_section_exact_after_adapter == 1u &&
        report.bridge.fifth_backing_fnv_after_adapter ==
            UINT64_C(0xD0D16B728ECA1764) &&
        report.bridge.sixth_thunk == kExpectedSixthThunk &&
        report.bridge.sixth_lr == kExpectedSixthReturn &&
        report.bridge.sixth_r3_input == kExpectedSixthBasePointer &&
        report.bridge.sixth_r4_input == kExpectedSixthSizePointer &&
        report.bridge.sixth_r5_input == 0x60001000u &&
        report.bridge.sixth_r6_input == VC_APF_X_PAGE_READWRITE &&
        report.bridge.sixth_r7_input == 0u &&
        report.bridge.sixth_r3_output == VC_APF_X_STATUS_SUCCESS &&
        report.bridge.sixth_base_before == 0x40000000u &&
        report.bridge.sixth_size_before == 0x00010060u &&
        report.bridge.sixth_base_after == 0x40000000u &&
        report.bridge.sixth_size_after == 0x00020000u &&
        report.bridge.sixth_instruction_count == 1079u &&
        report.bridge.sixth_vm_ledger_exact_before_adapter == 1u &&
        report.bridge.sixth_backing_exact_before_adapter == 1u &&
        report.bridge.sixth_backing_fnv_before_adapter ==
            UINT64_C(0xA2F6E3132B6EE02A) &&
        report.bridge.sixth_vm_ledger_exact_after_adapter == 1u &&
        report.bridge.sixth_backing_exact_after_adapter == 1u &&
        report.bridge.sixth_new_page_zeroed_after_adapter == 1u &&
        report.bridge.sixth_backing_fnv_after_adapter ==
            UINT64_C(0x90DE5290624DE02A) &&
        report.vm_page_count == 4096u &&
        report.vm_allocation_count == 1u &&
        report.reserved_page_count == 14u &&
        report.committed_page_count == 2u &&
        report.vm_ledger_exact == 1u &&
        report.initialized_page_exact == 1u &&
        report.remaining_backing_pattern_exact == 1u &&
        report.backing_fnv_before == UINT64_C(0x1F5E0DF9BC822325) &&
        report.backing_fnv_after == UINT64_C(0x90DE5290624DE02A);
    if (report.outcome == child_outcome::expected_sixth_boundary &&
        !expected) {
        report.outcome = child_outcome::unexpected_exception;
    }
'''
    source = source[:expected_start] + expected + source[expected_end:]

    print_start_marker = (
        '    std::printf(\n'
        '        "APF_GUARDED_SIXTH_BOUNDARY_CHILD_RESULT outcome=%s signal=0 "'
    )
    print_start = source.index(print_start_marker)
    print_end = source.index(
        "    for (std::uint32_t index = 0u; index < report.trace_count; ++index)",
        print_start)
    print_block = r'''    std::printf(
        "APF_GUARDED_SIXTH_BOUNDARY_CHILD_RESULT outcome=%s signal=0 "
        "entry_authorized=%u entry_called=%u prerequisite_step=%u "
        "gate_status=%u adapter_status=%u thunk=0x%08X stage=%u "
        "instructions=%llu function_dispatches=%llu last_pc=0x%08X "
        "lr=0x%08X r3=0x%08X first_instructions=%u "
        "second_instructions=%u third_instructions=%u "
        "fourth_instructions=%u fifth_instructions=%u "
        "fifth_thunk=0x%08X fifth_lr=0x%08X fifth_cs_exact=%u "
        "fifth_fnv_after=0x%016llX sixth_instructions=%u "
        "sixth_thunk=0x%08X sixth_lr=0x%08X sixth_r3_in=0x%08X "
        "sixth_r4_in=0x%08X sixth_r5_in=0x%08X sixth_r6_in=0x%08X "
        "sixth_r7_in=0x%08X sixth_r3_out=0x%08X "
        "sixth_base_before=0x%08X sixth_size_before=0x%08X "
        "sixth_base_after=0x%08X sixth_size_after=0x%08X "
        "sixth_ledger_before=%u sixth_backing_before=%u "
        "sixth_fnv_before=0x%016llX sixth_ledger_after=%u "
        "sixth_backing_after=%u sixth_new_page_zero=%u "
        "sixth_fnv_after=0x%016llX vm_pages=%u vm_allocations=%u "
        "reserved_pages=%u committed_pages=%u ledger_exact=%u "
        "initialized_page_exact=%u remaining_pattern_exact=%u "
        "backing_fnv_before=0x%016llX backing_fnv_after=0x%016llX trace=",
        outcome_name(report.outcome), report.entry_authorized,
        report.entry_called, report.prerequisite_step, report.gate_status,
        report.adapter_status, report.import_thunk, report.bridge.stage,
        static_cast<unsigned long long>(report.instructions_consumed),
        static_cast<unsigned long long>(report.function_dispatches_consumed),
        report.last_guest_address, report.context_lr, report.context_r3,
        report.bridge.first_instruction_count,
        report.bridge.second_instruction_count,
        report.bridge.third_instruction_count,
        report.bridge.fourth_instruction_count,
        report.bridge.fifth_instruction_count,
        report.bridge.fifth_thunk, report.bridge.fifth_lr,
        report.bridge.fifth_critical_section_exact_after_adapter,
        static_cast<unsigned long long>(
            report.bridge.fifth_backing_fnv_after_adapter),
        report.bridge.sixth_instruction_count,
        report.bridge.sixth_thunk, report.bridge.sixth_lr,
        report.bridge.sixth_r3_input, report.bridge.sixth_r4_input,
        report.bridge.sixth_r5_input, report.bridge.sixth_r6_input,
        report.bridge.sixth_r7_input, report.bridge.sixth_r3_output,
        report.bridge.sixth_base_before, report.bridge.sixth_size_before,
        report.bridge.sixth_base_after, report.bridge.sixth_size_after,
        report.bridge.sixth_vm_ledger_exact_before_adapter,
        report.bridge.sixth_backing_exact_before_adapter,
        static_cast<unsigned long long>(
            report.bridge.sixth_backing_fnv_before_adapter),
        report.bridge.sixth_vm_ledger_exact_after_adapter,
        report.bridge.sixth_backing_exact_after_adapter,
        report.bridge.sixth_new_page_zeroed_after_adapter,
        static_cast<unsigned long long>(
            report.bridge.sixth_backing_fnv_after_adapter),
        report.vm_page_count, report.vm_allocation_count,
        report.reserved_page_count, report.committed_page_count,
        report.vm_ledger_exact, report.initialized_page_exact,
        report.remaining_backing_pattern_exact,
        static_cast<unsigned long long>(report.backing_fnv_before),
        static_cast<unsigned long long>(report.backing_fnv_after));
'''
    return source[:print_start] + print_block + source[print_end:]


def parse_result_line(line: str) -> dict[str, str]:
    require(line.startswith(RESULT_PREFIX), "sixth result prefix changed")
    fields: dict[str, str] = {}
    for token in line[len(RESULT_PREFIX):].split():
        if "=" in token:
            key, value = token.split("=", 1)
            fields[key] = value
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--decoded", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--temp-root", type=Path, default=Path(".codex-tmp"))
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--clangxx", default="clang++-18")
    parser.add_argument("--jobs", type=int,
                        default=min(12, os.cpu_count() or 1))
    args = parser.parse_args()

    root = args.root.resolve()
    resolve = lambda path: path.resolve() if path.is_absolute() else \
        (root / path).resolve()
    decoded = resolve(args.decoded)
    output_json = resolve(args.json)
    transcript = resolve(args.transcript)
    temp_root = resolve(args.temp_root)
    xex = root / "extracted/All-Pro Football 2K8 (USA)/default.xex"
    volume = root / "extracted/All-Pro Football 2K8 (USA)/0A"
    fifth_report_path = root / (
        "reports/static_recomp/apf2k8_guarded_fifth_boundary_execution.json")
    static_path = root / (
        "reports/static_recomp/apf2k8_post_critical_section_static.json")
    composed_report_path = root / (
        "reports/static_recomp/"
        "apf2k8_static_recomp_opcode_switch_composed.json")
    budget_report_path = root / (
        "reports/static_recomp/"
        "apf2k8_guest_instruction_budget_instrumentation.json")
    leaf_report_path = root / (
        "reports/static_recomp/apf2k8_boot_leaf_adapters.json")
    xex_report_path = root / "reports/headers/apf2k8_xex_report.json"
    composed = root / "build-static-recomp-apf/ppc-opcode-switch-composed"
    generated = root / (
        "build-static-recomp-apf/ppc-opcode-switch-budget-instrumented")
    first_bridge_path = root / (
        "src/static_runtime/apf_first_entry_xenon_bridge.cpp")
    budget_source_path = root / (
        "src/static_runtime/apf_guest_instruction_budget.cpp")
    fifth_driver_path = root / "tools/apf_guarded_fifth_boundary_execute.py"
    static_analyzer_path = root / "tools/apf_post_critical_section_static.py"
    clang = shutil.which(args.clang)
    clangxx = shutil.which(args.clangxx)
    required = [
        decoded, xex, volume, fifth_report_path, static_path,
        composed_report_path, budget_report_path, leaf_report_path,
        xex_report_path, first_bridge_path, budget_source_path,
        fifth_driver_path, static_analyzer_path,
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "src/static_runtime/apf_boot_leaf_adapters.c",
    ]
    require(args.jobs > 0 and clang is not None and clangxx is not None and
            all(path.is_file() and not path.is_symlink() for path in required),
            "sixth-boundary prerequisite missing")
    require(sha256_file(xex) == EXPECTED_XEX_SHA256 and
            sha256_file(volume) == EXPECTED_VOLUME_SHA256 and
            decoded.stat().st_size == EXPECTED_DECODED_SIZE and
            sha256_file(decoded) == EXPECTED_DECODED_SHA256,
            "retail or decoded APF input changed")
    require(sha256_file(fifth_report_path) ==
                EXPECTED_FIFTH_REPORT_SHA256 and
            sha256_file(static_path) == EXPECTED_POST_CRITICAL_STATIC_SHA256 and
            sha256_file(fifth_driver_path) == EXPECTED_FIFTH_DRIVER_SHA256 and
            sha256_file(static_analyzer_path) ==
                EXPECTED_POST_CRITICAL_ANALYZER_SHA256 and
            sha256_file(first_bridge_path) == EXPECTED_FIRST_BRIDGE_SHA256 and
            sha256_file(budget_source_path) == EXPECTED_BUDGET_SOURCE_SHA256 and
            sha256_file(leaf_report_path) == EXPECTED_LEAF_REPORT_SHA256 and
            sha256_file(composed_report_path) ==
                EXPECTED_COMPOSED_REPORT_SHA256 and
            sha256_file(budget_report_path) == EXPECTED_BUDGET_REPORT_SHA256,
            "pinned APF evidence changed")

    prior = json.loads(fifth_report_path.read_text(encoding="utf-8"))
    static = json.loads(static_path.read_text(encoding="utf-8"))
    require(
        prior["result"]["child_outcome"] == "expected_fifth_boundary" and
        prior["generated_execution"]["executed_guest_instruction_count"] ==
            1019 and
        static["schema"] == "apf2k8_post_critical_section_static/v1" and
        static["static_trace"][
            "continuation_instruction_count_through_next_call"] == 60 and
        static["static_trace"][
            "cumulative_instruction_count_through_next_call"] == 1079 and
        static["static_trace"]["ordered_pc_sha256"] ==
            EXPECTED_CONTINUATION_TRACE_SHA256 and
        static["next_boundary"]["call_pc"] == "0x84BECE14" and
        static["next_boundary"]["return_pc"] == "0x84BECE18" and
        static["next_boundary"]["thunk"] == "0x84D0863C",
        "sixth static or dynamic prerequisite changed")

    composed_report = json.loads(composed_report_path.read_text(encoding="utf-8"))
    budget_report = json.loads(budget_report_path.read_text(encoding="utf-8"))
    composed_roster = first.exact_roster(composed)
    generated_roster = first.exact_roster(generated)
    require(first.composed_tree_sha256(composed_roster) ==
                EXPECTED_COMPOSED_TREE_SHA256 and
            first.budget_tree_sha256(generated, generated_roster) ==
                EXPECTED_INSTRUMENTED_TREE_SHA256,
            "complete generated tree changed")
    numbered = [generated / f"ppc_recomp.{index}.cpp"
                for index in range(EXPECTED_NUMBERED_COUNT)]
    rows = {item["path"]: item for item in budget_report["files"]}
    require(all(rows[path.name]["instrumented_sha256"] == sha256_file(path)
                for path in numbered), "instrumented TU changed")
    hook_count = sum(path.read_text(encoding="utf-8").count(
        "VC_APF_GUEST_INSTRUCTION_STEP(") for path in numbered)
    mapping_text = (generated / "ppc_func_mapping.cpp").read_text(
        encoding="utf-8")
    mapping_count = len(re.findall(
        r"^\s*\{ 0x[0-9A-F]+, [A-Za-z_][A-Za-z0-9_]* \},$",
        mapping_text, re.MULTILINE))
    require(hook_count == EXPECTED_HOOK_COUNT and
            mapping_count == EXPECTED_MAPPING_COUNT and
            budget_report["coverage_proof"]["hook_manifest_sha256"] ==
                EXPECTED_HOOK_MANIFEST_SHA256 and
            composed_report["result"]["unrecognized_instruction_count"] == 0,
            "generated coverage gate changed")

    xex_report = json.loads(xex_report_path.read_text(encoding="utf-8"))
    all_imports = {"__imp__" + item["name"]
                   for item in xex_report["imports"]["items"]
                   if item["thunk_address"] is not None}
    original_bridge = first_bridge_path.read_text(encoding="utf-8")
    typed_imports = set(re.findall(
        r"^VC_APF_DEFINE_IMPORT\((__imp__[A-Za-z0-9_]+),",
        original_bridge, re.MULTILINE))
    require(len(all_imports) == EXPECTED_IMPORT_COUNT and
            len(typed_imports) == EXPECTED_TYPED_IMPORT_COUNT and
            typed_imports < all_imports, "typed import split changed")
    nonfrontier = sorted(all_imports - typed_imports)

    bridge = specialized_bridge_source(original_bridge)
    budget = specialized_budget_source(
        budget_source_path.read_text(encoding="utf-8"))
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apf-sixth-boundary-v1-",
                                     dir=temp_root) as temporary:
        build = Path(temporary)
        files = {
            "abort": build / "nonfrontier_abort.h",
            "stubs": build / "nonfrontier_imports.cpp",
            "evidence": build / "sixth_boundary_evidence.h",
            "bridge": build / "sixth_boundary_bridge.cpp",
            "budget": build / "sixth_boundary_budget.cpp",
            "harness": build / "guarded_sixth_driver.cpp",
        }
        files["abort"].write_text(first.nonfrontier_header_source(),
                                  encoding="utf-8")
        files["stubs"].write_text(first.nonfrontier_stub_source(nonfrontier),
                                  encoding="utf-8")
        files["evidence"].write_text(evidence_header_source(), encoding="utf-8")
        files["bridge"].write_text(bridge, encoding="utf-8")
        files["budget"].write_text(budget, encoding="utf-8")
        files["harness"].write_text(harness_source(), encoding="utf-8")
        cpp_sources = [
            generated / "ppc_func_mapping.cpp", *numbered,
            files["bridge"], files["budget"], files["stubs"], files["harness"],
        ]
        c_sources = [
            root / "src/static_runtime/apf_first_entry_gate.c",
            root / "src/static_runtime/apf_imported_data_bootstrap.c",
            root / "src/static_runtime/apf_boot_leaf_adapters.c",
        ]
        includes = [
            root / "include", generated, build,
            root / "tools/vendor/XenonRecomp/XenonUtils",
            root / "tools/vendor/XenonRecomp/thirdparty/simde",
        ]
        specs: list[tuple[list[str], Path]] = []
        for index, source_path in enumerate(cpp_sources):
            target = build / f"cpp-{index:03d}.o"
            command = [clangxx, "-std=c++20", "-O0", "-c",
                       str(source_path), "-o", str(target)]
            command.extend(f"-I{path}" for path in includes)
            specs.append((command, target))
        for index, source_path in enumerate(c_sources):
            target = build / f"c-{index:03d}.o"
            specs.append(([clang, "-std=c11", "-O0", "-D_GNU_SOURCE", "-c",
                           str(source_path), "-o", str(target),
                           f"-I{root / 'include'}"], target))
        outcomes: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {executor.submit(first.compile_one, command, target): target
                       for command, target in specs}
            for future in as_completed(futures):
                outcomes.append(future.result())
        failures = [item for item in outcomes if item["return_code"] != 0]
        require(not failures, "sixth-boundary compilation failed: " +
                " | ".join(item["stderr"][-2000:] for item in failures[:3]))
        executable = build / "apf_guarded_sixth_boundary_v1"
        linked = subprocess.run([
            clangxx, "-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie",
            *[str(target) for _, target in specs], "-lm", "-o", str(executable),
        ], capture_output=True, text=True, check=False)
        require(linked.returncode == 0,
                "sixth-boundary link failed: " + linked.stderr[-2400:])
        executed = subprocess.run([
            str(executable), str(decoded), str(xex), AUTHORIZATION_TOKEN,
        ], capture_output=True, text=True, check=False, timeout=30)
        require(executed.returncode == 0,
                f"sixth child changed ({executed.returncode}): " +
                executed.stdout + executed.stderr[-2400:])
        lines = [line for line in executed.stdout.splitlines()
                 if line.startswith(RESULT_PREFIX)]
        require(len(lines) == 1 and executed.stderr == "",
                "sixth child transcript changed")
        result_line = lines[0]
        fields = parse_result_line(result_line)

    exact = {
        "outcome": "expected_sixth_boundary", "signal": "0",
        "entry_authorized": "1", "entry_called": "1",
        "prerequisite_step": "6", "gate_status": "0",
        "adapter_status": "0", "stage": "6", "instructions": "1079",
        "function_dispatches": "6", "first_instructions": "38",
        "second_instructions": "264", "third_instructions": "283",
        "fourth_instructions": "365", "fifth_instructions": "1019",
        "fifth_cs_exact": "1", "sixth_instructions": "1079",
        "sixth_ledger_before": "1", "sixth_backing_before": "1",
        "sixth_ledger_after": "1", "sixth_backing_after": "1",
        "sixth_new_page_zero": "1", "reserved_pages": "14",
        "committed_pages": "2", "ledger_exact": "1",
        "initialized_page_exact": "1", "remaining_pattern_exact": "1",
        "containment_normal": "1", "containment_signal": "1",
        "containment_timeout": "1",
    }
    require(all(fields.get(key) == value for key, value in exact.items()),
            "sixth result scalar changed")
    expected_hex = {
        "thunk": EXPECTED_SIXTH_THUNK,
        "last_pc": EXPECTED_SIXTH_CALL,
        "lr": EXPECTED_SIXTH_RETURN,
        "r3": 0,
        "fifth_thunk": fifth.EXPECTED_FIFTH_THUNK,
        "fifth_lr": fifth.EXPECTED_FIFTH_RETURN,
        "fifth_fnv_after": fifth.EXPECTED_POST_FIFTH_BACKING_FNV,
        "sixth_thunk": EXPECTED_SIXTH_THUNK,
        "sixth_lr": EXPECTED_SIXTH_RETURN,
        "sixth_r3_in": EXPECTED_BASE_POINTER,
        "sixth_r4_in": EXPECTED_SIZE_POINTER,
        "sixth_r5_in": 0x60001000,
        "sixth_r6_in": 4,
        "sixth_r7_in": 0,
        "sixth_r3_out": 0,
        "sixth_base_before": EXPECTED_REQUESTED_BASE,
        "sixth_size_before": EXPECTED_REQUESTED_SIZE,
        "sixth_base_after": EXPECTED_REQUESTED_BASE,
        "sixth_size_after": EXPECTED_ADJUSTED_SIZE,
        "sixth_fnv_before": EXPECTED_PRE_SIXTH_BACKING_FNV,
        "sixth_fnv_after": EXPECTED_POST_SIXTH_BACKING_FNV,
        "backing_fnv_before": 0x1F5E0DF9BC822325,
        "backing_fnv_after": EXPECTED_POST_SIXTH_BACKING_FNV,
    }
    require(all(int(fields.get(key, "-1"), 0) == value
                for key, value in expected_hex.items()),
            "sixth ABI/state changed")
    trace = [int(value, 16) for value in fields["trace"].split(",") if value]
    prior_pcs = [int(value, 16) for value in
                 prior["generated_execution"]["ordered_guest_pcs"]]
    require(len(trace) == EXPECTED_CUMULATIVE_INSTRUCTIONS and
            trace[:1019] == prior_pcs and trace[1019] == fifth.EXPECTED_FIFTH_RETURN and
            trace[-1] == EXPECTED_SIXTH_CALL,
            "sixth dynamic trace endpoints changed")
    continuation = trace[1019:]
    continuation_sha = trace_sha256(continuation)
    require(len(continuation) == EXPECTED_CONTINUATION_INSTRUCTIONS and
            continuation_sha == EXPECTED_CONTINUATION_TRACE_SHA256 ==
                static["static_trace"]["ordered_pc_sha256"],
            "sixth dynamic/static trace mismatch")

    local_files = [
        first_bridge_path, budget_source_path,
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "src/static_runtime/apf_boot_leaf_adapters.c",
        fifth_driver_path, static_analyzer_path,
        root / "tools/apf_guarded_sixth_boundary_execute.py",
    ]
    report = {
        "schema": SCHEMA,
        "result": {
            "guarded_fifth_boundary_execution_revalidated": True,
            "post_critical_section_static_proof_revalidated": True,
            "translated_title_code_executed": True,
            "continued_past_fifth_typed_boundary": True,
            "expected_sixth_typed_boundary_reached": True,
            "sixth_typed_adapter_completed": True,
            "continued_past_sixth_typed_boundary": False,
            "child_outcome": fields["outcome"],
            "signal_number": 0,
            "native_boot_proved": False,
            "main_menu_proved": False,
        },
        "authorization_gates": {
            "retail_xex_sha256_exact": True,
            "retail_volume_sha256_exact": True,
            "decoded_image_sha256_and_size_exact": True,
            "guarded_fifth_report_exact": True,
            "post_critical_section_static_report_exact": True,
            "composed_and_instrumented_complete_trees_exact": True,
            "instruction_hook_count": hook_count,
            "mapping_count": mapping_count,
            "typed_import_count": len(typed_imports),
            "sixth_dynamic_pc_lr_register_cell_vm_backing_gate": True,
            "instruction_limit": INSTRUCTION_LIMIT,
            "function_dispatch_limit": FUNCTION_DISPATCH_LIMIT,
            "timeout_milliseconds": 5000,
            "containment_normal_signal_timeout_revalidated": True,
        },
        "generated_execution": {
            "entry": f"0x{EXPECTED_ENTRY:08X}",
            "executed_guest_instruction_count": len(trace),
            "function_dispatch_count": int(fields["function_dispatches"]),
            "last_executed_guest_pc": f"0x{trace[-1]:08X}",
            "full_ordered_pc_sha256": trace_sha256(trace),
            "post_critical_section_ordered_pc_sha256": continuation_sha,
            "ordered_guest_pcs": [f"0x{pc:08X}" for pc in trace],
            "sixth_boundary": {
                "import": "NtAllocateVirtualMemory",
                "operation": "overlapping commit inside existing reservation",
                "call_pc": f"0x{EXPECTED_SIXTH_CALL:08X}",
                "return_pc": f"0x{EXPECTED_SIXTH_RETURN:08X}",
                "thunk": f"0x{EXPECTED_SIXTH_THUNK:08X}",
                "instruction_count_at_call": len(trace),
                "arguments": {
                    "r3_base_pointer": fields["sixth_r3_in"],
                    "base_value_before": fields["sixth_base_before"],
                    "r4_size_pointer": fields["sixth_r4_in"],
                    "size_value_before": fields["sixth_size_before"],
                    "r5_allocation_type": fields["sixth_r5_in"],
                    "r6_protection": fields["sixth_r6_in"],
                    "r7_debug_memory": fields["sixth_r7_in"],
                },
                "result_ntstatus": fields["sixth_r3_out"],
                "base_value_after": fields["sixth_base_after"],
                "size_value_after": fields["sixth_size_after"],
                "newly_committed_page_zeroed_exact": True,
                "adapter_status": "ok",
                "generated_return_instruction_executed": False,
                "terminal_semantics": (
                    "exact-site typed overlap-commit adapter completed; "
                    "bridge threw before generated instruction 0x84BECE18"
                ),
            },
        },
        "virtual_memory_and_initialization": {
            "active_allocation_count": 1,
            "allocation_page_count": 16,
            "pre_adapter_committed_page_count": 1,
            "pre_adapter_reserved_page_count": 15,
            "post_adapter_committed_page_count": 2,
            "post_adapter_reserved_page_count": 14,
            "vm_ledger_exact": True,
            "first_page_sha256_before_adapter":
                EXPECTED_PRE_SIXTH_PAGE_SHA256,
            "first_page_nonzero_byte_count": 814,
            "pre_adapter_allocation_fnv1a64": fields["sixth_fnv_before"],
            "post_adapter_allocation_fnv1a64": fields["sixth_fnv_after"],
            "newly_committed_second_page_zeroed": True,
            "remaining_14_page_pattern_exact": True,
        },
        "inputs": {
            "retail_xex": pin(xex, root),
            "retail_volume": pin(volume, root),
            "decoded_image": {
                "size": decoded.stat().st_size,
                "sha256": sha256_file(decoded),
                "temporary_validator_artifact": True,
            },
            "guarded_fifth_report": pin(fifth_report_path, root),
            "post_critical_section_static_report": pin(static_path, root),
            "composed_report": pin(composed_report_path, root),
            "budget_report": pin(budget_report_path, root),
            "typed_leaf_report": pin(leaf_report_path, root),
            "local_files": [pin(path, root) for path in local_files],
        },
        "isolation": {
            "normal_host_shell_linked": False,
            "normal_host_shell_modified": False,
            "retail_inputs_modified": False,
            "guest_execution_process": "forked bounded child",
            "temporary_generated_objects_deleted": True,
        },
        "portme": [
            "// PORTME at 0x84BECE18: statically prove and type the next exact boundary before authorizing any further generated instruction.",
            "// PORTME: replace nonfrontier import abort definitions only as their exact guest paths become reachable.",
            "// PORTME: retain complete instruction, dispatch, signal, and timeout containment while expanding startup execution.",
        ],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(result_line + "\n", encoding="utf-8")
    print(result_line)
    print(
        "APF_GUARDED_SIXTH_BOUNDARY_EXECUTION_PASS instructions=1079 "
        "function_dispatches=6 sixth=0x84BECE14 overlap_commit=0x00020000 "
        "committed_pages=2 reserved_pages=14 continued_after_sixth=0 "
        "native_boot=0 temporary_outputs_deleted=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
