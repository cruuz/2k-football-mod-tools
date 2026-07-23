#!/usr/bin/env python3
"""Execute APF through exactly its third typed boundary in isolation.

The only newly authorized continuation starts at the proved post-reserve
return PC 0x84BED7BC.  A throwaway bridge dynamically revalidates the first
header query and second reserve boundary, then requires a distinct token,
stage, PC/LR, ABI, instruction ledger, VM ledger, and backing pattern before
allowing the 19-instruction continuation.  It dispatches only the existing
typed NtAllocateVirtualMemory commit adapter at 0x84BED808 and throws before
the generated instruction at 0x84BED80C.  All translated execution occurs in
a bounded forked child.
"""

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


SCHEMA = "apf2k8_guarded_third_boundary_execution/v1"
EXPECTED_XEX_SHA256 = first.EXPECTED_XEX_SHA256
EXPECTED_VOLUME_SHA256 = first.EXPECTED_VOLUME_SHA256
EXPECTED_DECODED_SHA256 = first.EXPECTED_DECODED_SHA256
EXPECTED_DECODED_SIZE = first.EXPECTED_DECODED_SIZE
EXPECTED_COMPOSED_REPORT_SHA256 = first.EXPECTED_COMPOSED_REPORT_SHA256
EXPECTED_BUDGET_REPORT_SHA256 = first.EXPECTED_BUDGET_REPORT_SHA256
EXPECTED_COMPOSED_TREE_SHA256 = first.EXPECTED_COMPOSED_TREE_SHA256
EXPECTED_INSTRUMENTED_TREE_SHA256 = first.EXPECTED_INSTRUMENTED_TREE_SHA256
EXPECTED_HOOK_MANIFEST_SHA256 = first.EXPECTED_HOOK_MANIFEST_SHA256
EXPECTED_NUMBERED_COUNT = first.EXPECTED_NUMBERED_COUNT
EXPECTED_CPP_COUNT = first.EXPECTED_CPP_COUNT
EXPECTED_MAPPING_COUNT = first.EXPECTED_MAPPING_COUNT
EXPECTED_IMPLEMENTATION_COUNT = first.EXPECTED_IMPLEMENTATION_COUNT
EXPECTED_HOOK_COUNT = first.EXPECTED_HOOK_COUNT
EXPECTED_IMPORT_COUNT = first.EXPECTED_IMPORT_COUNT
EXPECTED_TYPED_IMPORT_COUNT = first.EXPECTED_TYPED_IMPORT_COUNT
EXPECTED_ENTRY = first.EXPECTED_ENTRY

EXPECTED_FIRST_REPORT_SHA256 = (
    "81a3f676a5985290a89a83aaf14543893bf0d97888b88764a24ccb337687cbca"
)
EXPECTED_SECOND_STATIC_SHA256 = (
    "16f95dced67f975cbf4e4636a51d277c23d2ed1f5b7578d6b0704c27993802a0"
)
EXPECTED_SECOND_EXECUTION_SHA256 = (
    "d60c0116a5445624453d867c8600c0466b06a0fb64f3bc183c7ebe730c651761"
)
EXPECTED_POST_RESERVE_STATIC_SHA256 = (
    "1a0b9ac08bc17007a7d7922024d6703eab702fb900bf60d08bbc84fda566cc2c"
)
EXPECTED_LEAF_REPORT_SHA256 = (
    "6b7b7d65bb5d0cc5d90bc7dd4abb34b8b3a780a9e3be7e57afb1946a260f0b5e"
)
EXPECTED_FIRST_BRIDGE_SHA256 = (
    "f4f7cc44253bfacf6faf0520de28bd35d0c544928c1d9b415d7b9041fb4a9e1d"
)
EXPECTED_BUDGET_SOURCE_SHA256 = (
    "7eaffceb307f079d4259ac7519ae62112b40623fb357695e1047614d8a362679"
)
EXPECTED_FIRST_DRIVER_SHA256 = (
    "2bed95f7e30ed211b602bcf50acc51abb05b16241b050c66a7b50e98e5e8bebd"
)
EXPECTED_SECOND_DRIVER_SHA256 = (
    "f8b91d4dc4d0d4eef4ea485984fb746f06c2e6df0b11d028ed6b9accfc30d664"
)
EXPECTED_POST_RESERVE_ANALYZER_SHA256 = (
    "4fb5c9272510eab72e56e2d626e213e08a9cc8e38ee4b54507a0b062c38a42ba"
)

EXPECTED_FIRST_CALL = 0x84BF1888
EXPECTED_FIRST_RETURN = 0x84BF188C
EXPECTED_FIRST_THUNK = 0x84D0859C
EXPECTED_SECOND_CALL = 0x84BED7B8
EXPECTED_SECOND_RETURN = 0x84BED7BC
EXPECTED_SECOND_THUNK = 0x84D0863C
EXPECTED_THIRD_CALL = 0x84BED808
EXPECTED_THIRD_RETURN = 0x84BED80C
EXPECTED_THIRD_THUNK = 0x84D0863C
EXPECTED_FIRST_INSTRUCTIONS = 38
EXPECTED_CONTINUATION_INSTRUCTIONS = 226
EXPECTED_CUMULATIVE_INSTRUCTIONS = 264
EXPECTED_CONTINUATION_TRACE_SHA256 = (
    "764c6c72387763e12d8338d9d437b2b815e64f29f88c10cedd761aa334bf31ec"
)
EXPECTED_POST_RESERVE_INSTRUCTIONS = 19
EXPECTED_THIRD_CUMULATIVE_INSTRUCTIONS = 283
EXPECTED_POST_RESERVE_TRACE_SHA256 = (
    "df3f3f6aec6fd3b6dbede92272b7a2ae22a6cbba63c9c60d0d9c4d4e9fe638fd"
)
EXPECTED_BASE_POINTER = 0x7001FC50
EXPECTED_SIZE_POINTER = 0x7001FD34
EXPECTED_REQUESTED_SIZE = 0x00100000
EXPECTED_ALLOCATED_BASE = 0x40000000
EXPECTED_ALLOCATION_TYPE = 0x60002000
EXPECTED_COMMIT_BASE_POINTER = 0x7001FC54
EXPECTED_COMMIT_SIZE_POINTER = 0x7001FD3C
EXPECTED_COMMIT_SIZE = 0x00010000
EXPECTED_COMMIT_ALLOCATION_TYPE = 0x60001000
EXPECTED_PROTECT = 0x00000004
EXPECTED_VM_PAGE_COUNT = 4096
EXPECTED_RESERVED_PAGES = 16
EXPECTED_COMMITTED_PAGES = 1
EXPECTED_FUNCTION_DISPATCHES = 3
EXPECTED_BACKING_FNV_BEFORE = 0x1F5E0DF9BC822325
EXPECTED_BACKING_FNV_AFTER = 0x8179632E8A902325
INSTRUCTION_LIMIT = 4096
FUNCTION_DISPATCH_LIMIT = 64
AUTHORIZATION_TOKEN = (
    "apf2k8-v1:d60c0116:1a0b9ac0:981a5714:cde5b922:third-boundary-commit-only"
)
AUTHORIZATION_NONCE = 0xA2F23008D80880C3
RESULT_PREFIX = "APF_GUARDED_THIRD_BOUNDARY_CHILD_RESULT "


class ThirdBoundaryError(RuntimeError):
    """Fail-closed authorization or execution mismatch."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ThirdBoundaryError(message)


def sha256_file(path: Path) -> str:
    return first.sha256_file(path)


def relative(path: Path, root: Path) -> str:
    return first.relative(path, root)


def pin(path: Path, root: Path) -> dict[str, Any]:
    return first.pin(path, root)


def evidence_header_source() -> str:
    return r'''#pragma once
#include "static_runtime/apf_first_entry_gate.h"

#include <cstddef>
#include <cstdint>

struct vc_apf_third_boundary_bridge_evidence {
    std::uint32_t stage;
    std::uint32_t first_thunk;
    std::uint32_t first_lr;
    std::uint32_t first_r3_input;
    std::uint32_t first_r4_input;
    std::uint32_t first_r3_output;
    std::uint32_t first_instruction_count;
    std::uint32_t second_thunk;
    std::uint32_t second_lr;
    std::uint32_t second_r3_input;
    std::uint32_t second_r4_input;
    std::uint32_t second_r5_input;
    std::uint32_t second_r6_input;
    std::uint32_t second_r7_input;
    std::uint32_t second_base_value_before;
    std::uint32_t second_size_value_before;
    std::uint32_t second_r3_output;
    std::uint32_t second_instruction_count;
    std::uint32_t reserve_vm_ledger_exact_before_continuation;
    std::uint32_t reserve_backing_pattern_exact_before_continuation;
    std::uint64_t reserve_backing_fnv_before_continuation;
    std::uint32_t third_thunk;
    std::uint32_t third_lr;
    std::uint32_t third_r3_input;
    std::uint32_t third_r4_input;
    std::uint32_t third_r5_input;
    std::uint32_t third_r6_input;
    std::uint32_t third_r7_input;
    std::uint32_t third_base_value_before;
    std::uint32_t third_size_value_before;
    std::uint32_t third_r3_output;
    std::uint32_t third_base_value_after;
    std::uint32_t third_size_value_after;
    std::uint32_t third_instruction_count;
};

bool vc_apf_third_boundary_mode_arm(vc_apf_first_entry_state *state,
                                    std::uint64_t nonce);
void vc_apf_third_boundary_mode_evidence(
    vc_apf_third_boundary_bridge_evidence *evidence);
std::size_t vc_apf_third_boundary_full_trace_copy(
    std::uint32_t *addresses, std::size_t capacity);
'''


def specialized_bridge_source(original: str) -> str:
    """Derive an execution-only bridge from the exact pinned first bridge."""

    require(hashlib.sha256(original.encode("utf-8")).hexdigest() ==
            EXPECTED_FIRST_BRIDGE_SHA256,
            "first-boundary Xenon bridge source changed")
    include_marker = '#include "static_runtime/apf_first_entry_xenon_bridge.h"\n'
    require(original.count(include_marker) == 1,
            "bridge include marker changed")
    derived = original.replace(
        include_marker,
        include_marker + '#include "third_boundary_evidence.h"\n' +
        '#include "static_runtime/apf_guest_instruction_budget.h"\n',
        1)

    state_marker = (
        "thread_local vc_apf_first_entry_state *vc_apf_bound_state = nullptr;\n"
    )
    require(derived.count(state_marker) == 1,
            "bridge bound-state marker changed")
    derived = derived.replace(
        state_marker,
        state_marker +
        "thread_local bool vc_apf_third_boundary_armed = false;\n"
        "thread_local vc_apf_third_boundary_bridge_evidence "
        "vc_apf_third_boundary_observed{};\n",
        1)

    start = derived.find("[[noreturn]] void dispatch_and_stop(")
    end = derived.find("\nPPCFunc *expected_bridge", start)
    require(start >= 0 and end > start,
            "first-boundary dispatch body changed")
    replacement = r'''std::uint32_t load_bridge_be_u32(
    const std::uint8_t *bytes) {
    return (static_cast<std::uint32_t>(bytes[0]) << 24u) |
           (static_cast<std::uint32_t>(bytes[1]) << 16u) |
           (static_cast<std::uint32_t>(bytes[2]) << 8u) |
           static_cast<std::uint32_t>(bytes[3]);
}

std::uint64_t reserve_backing_fnv(const vc_apf_first_entry_state &state) {
    const std::uint8_t *const bytes =
        state.adapter_runtime->config.vm_backing_bytes;
    std::uint64_t value = UINT64_C(14695981039346656037);
    for (std::size_t index = 0u; index < 0x00100000u; ++index) {
        value ^= bytes[index];
        value *= UINT64_C(1099511628211);
    }
    return value;
}

bool reserve_backing_pattern_exact(const vc_apf_first_entry_state &state) {
    const std::uint8_t *const bytes =
        state.adapter_runtime->config.vm_backing_bytes;
    for (std::size_t index = 0u; index < 0x00100000u; ++index) {
        if (bytes[index] != static_cast<std::uint8_t>(
                (index * 131u + 17u) & 0xFFu)) {
            return false;
        }
    }
    return true;
}

bool reserve_vm_ledger_exact(const vc_apf_first_entry_state &state) {
    const vc_apf_boot_leaf_runtime &runtime = *state.adapter_runtime;
    if (runtime.vm_page_count != 4096u ||
        runtime.vm_allocation_count != 1u ||
        !runtime.vm_allocations[0].active ||
        runtime.vm_allocations[0].base_page != 0u ||
        runtime.vm_allocations[0].page_count != 16u ||
        runtime.vm_allocations[0].allocation_protect !=
            VC_APF_X_PAGE_READWRITE) {
        return false;
    }
    for (std::size_t index = 1u;
         index < VC_APF_BOOT_VM_MAX_ALLOCATIONS; ++index) {
        if (runtime.vm_allocations[index].active) return false;
    }
    for (std::size_t index = 0u; index < runtime.vm_page_count; ++index) {
        const vc_apf_boot_vm_page &page = runtime.vm_pages[index];
        if (index < 16u) {
            if (page.allocation_id != 1u || page.state != 1u ||
                page.protect != VC_APF_X_PAGE_READWRITE) return false;
        } else if (page.allocation_id != 0u || page.state != 0u ||
                   page.protect != 0u) {
            return false;
        }
    }
    return true;
}

void dispatch_and_stop(PPCContext &context, std::uint8_t *base,
                       std::uint32_t import_thunk) {
    vc_apf_guest_ppc_context adapter_context{};
    vc_apf_boot_leaf_status adapter_status = VC_APF_BOOT_LEAF_INVALID_ARGUMENT;
    vc_apf_first_entry_status gate_status = VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    vc_apf_guest_instruction_trace trace{};
    unsigned int index;

    auto stop = [&](vc_apf_first_entry_status gate,
                    vc_apf_boot_leaf_status adapter) -> void {
        throw vc_apf_first_entry_boundary_stop{gate, adapter, import_thunk};
    };
    if (vc_apf_bound_state == nullptr ||
        base != vc_apf_bound_state->guest_address_space ||
        !vc_apf_third_boundary_armed) {
        stop(VC_APF_FIRST_ENTRY_NOT_AUTHORIZED,
             VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    }
    for (index = 0u; index < 32u; ++index) {
        adapter_context.gpr[index] = read_gpr(context, index);
    }
    adapter_context.lr = static_cast<std::uint32_t>(context.lr);

    if (vc_apf_third_boundary_observed.stage == 0u) {
        if (import_thunk != VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK ||
            adapter_context.lr != VC_APF_FIRST_ENTRY_FIRST_IMPORT_RETURN ||
            adapter_context.gpr[3] !=
                vc_apf_bound_state->imported_data.raw_xex_prefix ||
            adapter_context.gpr[3] != UINT64_C(0x70020100) ||
            adapter_context.gpr[4] !=
                VC_APF_IMPORTED_DATA_XEX_DEFAULT_HEAP_SIZE ||
            vc_apf_bound_state->budget.function_dispatches_consumed != 0u ||
            vc_apf_guest_instruction_budget_snapshot(&trace) !=
                VC_APF_FIRST_ENTRY_OK ||
            trace.successful_instruction_count != 38u ||
            trace.recent_count == 0u ||
            trace.recent_addresses[trace.recent_count - 1u] !=
                VC_APF_FIRST_ENTRY_FIRST_IMPORT_CALL) {
            stop(VC_APF_FIRST_ENTRY_NOT_AUTHORIZED,
                 VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
        }
        vc_apf_third_boundary_observed.first_thunk = import_thunk;
        vc_apf_third_boundary_observed.first_lr = adapter_context.lr;
        vc_apf_third_boundary_observed.first_r3_input =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        vc_apf_third_boundary_observed.first_r4_input =
            static_cast<std::uint32_t>(adapter_context.gpr[4]);
        vc_apf_third_boundary_observed.first_instruction_count =
            static_cast<std::uint32_t>(trace.successful_instruction_count);
        gate_status = vc_apf_first_entry_dispatch_import(
            vc_apf_bound_state, &adapter_context, import_thunk,
            &adapter_status);
        for (index = 0u; index < 32u; ++index) {
            write_gpr(context, index, adapter_context.gpr[index]);
        }
        context.lr = adapter_context.lr;
        vc_apf_third_boundary_observed.first_r3_output =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        if (gate_status != VC_APF_FIRST_ENTRY_OK ||
            adapter_status != VC_APF_BOOT_LEAF_OK ||
            adapter_context.gpr[3] != 0u ||
            vc_apf_bound_state->first_boundary_thunk != import_thunk ||
            vc_apf_bound_state->first_boundary_adapter_status !=
                VC_APF_BOOT_LEAF_OK ||
            vc_apf_bound_state->budget.function_dispatches_consumed != 1u) {
            stop(gate_status, adapter_status);
        }
        vc_apf_third_boundary_observed.stage = 1u;
        return;
    }

    if (vc_apf_third_boundary_observed.stage == 1u) {
        if (import_thunk != VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY ||
            adapter_context.lr != 0x84BED7BCu ||
            adapter_context.gpr[3] != UINT64_C(0x7001FC50) ||
            adapter_context.gpr[4] != UINT64_C(0x7001FD34) ||
            adapter_context.gpr[5] != UINT64_C(0x60002000) ||
            adapter_context.gpr[6] != UINT64_C(0x00000004) ||
            adapter_context.gpr[7] != 0u ||
            vc_apf_bound_state->budget.function_dispatches_consumed != 1u ||
            vc_apf_guest_instruction_budget_snapshot(&trace) !=
                VC_APF_FIRST_ENTRY_OK ||
            trace.successful_instruction_count != 264u ||
            trace.recent_count == 0u ||
            trace.recent_addresses[trace.recent_count - 1u] !=
                0x84BED7B8u ||
            load_bridge_be_u32(base + 0x7001FC50u) != 0u ||
            load_bridge_be_u32(base + 0x7001FD34u) != 0x00100000u) {
            stop(VC_APF_FIRST_ENTRY_NOT_AUTHORIZED,
                 VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
        }
        vc_apf_third_boundary_observed.second_thunk = import_thunk;
        vc_apf_third_boundary_observed.second_lr = adapter_context.lr;
        vc_apf_third_boundary_observed.second_r3_input =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        vc_apf_third_boundary_observed.second_r4_input =
            static_cast<std::uint32_t>(adapter_context.gpr[4]);
        vc_apf_third_boundary_observed.second_r5_input =
            static_cast<std::uint32_t>(adapter_context.gpr[5]);
        vc_apf_third_boundary_observed.second_r6_input =
            static_cast<std::uint32_t>(adapter_context.gpr[6]);
        vc_apf_third_boundary_observed.second_r7_input =
            static_cast<std::uint32_t>(adapter_context.gpr[7]);
        vc_apf_third_boundary_observed.second_base_value_before =
            load_bridge_be_u32(base + 0x7001FC50u);
        vc_apf_third_boundary_observed.second_size_value_before =
            load_bridge_be_u32(base + 0x7001FD34u);
        vc_apf_third_boundary_observed.second_instruction_count =
            static_cast<std::uint32_t>(trace.successful_instruction_count);
        gate_status = vc_apf_first_entry_dispatch_import(
            vc_apf_bound_state, &adapter_context, import_thunk,
            &adapter_status);
        for (index = 0u; index < 32u; ++index) {
            write_gpr(context, index, adapter_context.gpr[index]);
        }
        context.lr = adapter_context.lr;
        vc_apf_third_boundary_observed.second_r3_output =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        const bool ledger_exact = reserve_vm_ledger_exact(
            *vc_apf_bound_state);
        const bool backing_exact = reserve_backing_pattern_exact(
            *vc_apf_bound_state);
        vc_apf_third_boundary_observed
            .reserve_vm_ledger_exact_before_continuation =
            ledger_exact ? 1u : 0u;
        vc_apf_third_boundary_observed
            .reserve_backing_pattern_exact_before_continuation =
            backing_exact ? 1u : 0u;
        vc_apf_third_boundary_observed
            .reserve_backing_fnv_before_continuation =
            reserve_backing_fnv(*vc_apf_bound_state);
        if (gate_status != VC_APF_FIRST_ENTRY_OK ||
            adapter_status != VC_APF_BOOT_LEAF_OK ||
            adapter_context.gpr[3] != VC_APF_X_STATUS_SUCCESS ||
            vc_apf_bound_state->budget.function_dispatches_consumed != 2u ||
            load_bridge_be_u32(base + 0x7001FC50u) != 0x40000000u ||
            load_bridge_be_u32(base + 0x7001FD34u) != 0x00100000u ||
            load_bridge_be_u32(base + 0x7001FD3Cu) != 0x00010000u ||
            !ledger_exact || !backing_exact ||
            vc_apf_third_boundary_observed
                    .reserve_backing_fnv_before_continuation !=
                UINT64_C(0x1F5E0DF9BC822325)) {
            stop(gate_status, adapter_status);
        }
        vc_apf_third_boundary_observed.stage = 2u;
        return;
    }

    if (vc_apf_third_boundary_observed.stage != 2u ||
        import_thunk != VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY ||
        adapter_context.lr != 0x84BED80Cu ||
        adapter_context.gpr[3] != UINT64_C(0x7001FC54) ||
        adapter_context.gpr[4] != UINT64_C(0x7001FD3C) ||
        adapter_context.gpr[5] != UINT64_C(0x60001000) ||
        adapter_context.gpr[6] != UINT64_C(0x00000004) ||
        adapter_context.gpr[7] != 0u ||
        vc_apf_bound_state->budget.function_dispatches_consumed != 2u ||
        vc_apf_guest_instruction_budget_snapshot(&trace) !=
            VC_APF_FIRST_ENTRY_OK ||
        trace.successful_instruction_count != 283u ||
        trace.recent_count == 0u ||
        trace.recent_addresses[trace.recent_count - 1u] != 0x84BED808u ||
        load_bridge_be_u32(base + 0x7001FC50u) != 0x40000000u ||
        load_bridge_be_u32(base + 0x7001FD34u) != 0x00100000u ||
        load_bridge_be_u32(base + 0x7001FC54u) != 0x40000000u ||
        load_bridge_be_u32(base + 0x7001FD3Cu) != 0x00010000u ||
        !reserve_vm_ledger_exact(*vc_apf_bound_state) ||
        !reserve_backing_pattern_exact(*vc_apf_bound_state) ||
        reserve_backing_fnv(*vc_apf_bound_state) !=
            UINT64_C(0x1F5E0DF9BC822325)) {
        stop(VC_APF_FIRST_ENTRY_NOT_AUTHORIZED,
             VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    }
    vc_apf_third_boundary_observed.third_thunk = import_thunk;
    vc_apf_third_boundary_observed.third_lr = adapter_context.lr;
    vc_apf_third_boundary_observed.third_r3_input =
        static_cast<std::uint32_t>(adapter_context.gpr[3]);
    vc_apf_third_boundary_observed.third_r4_input =
        static_cast<std::uint32_t>(adapter_context.gpr[4]);
    vc_apf_third_boundary_observed.third_r5_input =
        static_cast<std::uint32_t>(adapter_context.gpr[5]);
    vc_apf_third_boundary_observed.third_r6_input =
        static_cast<std::uint32_t>(adapter_context.gpr[6]);
    vc_apf_third_boundary_observed.third_r7_input =
        static_cast<std::uint32_t>(adapter_context.gpr[7]);
    vc_apf_third_boundary_observed.third_base_value_before =
        load_bridge_be_u32(base + 0x7001FC54u);
    vc_apf_third_boundary_observed.third_size_value_before =
        load_bridge_be_u32(base + 0x7001FD3Cu);
    vc_apf_third_boundary_observed.third_instruction_count =
        static_cast<std::uint32_t>(trace.successful_instruction_count);
    gate_status = vc_apf_first_entry_dispatch_import(
        vc_apf_bound_state, &adapter_context, import_thunk, &adapter_status);
    for (index = 0u; index < 32u; ++index) {
        write_gpr(context, index, adapter_context.gpr[index]);
    }
    context.lr = adapter_context.lr;
    vc_apf_third_boundary_observed.third_r3_output =
        static_cast<std::uint32_t>(adapter_context.gpr[3]);
    vc_apf_third_boundary_observed.third_base_value_after =
        load_bridge_be_u32(base + 0x7001FC54u);
    vc_apf_third_boundary_observed.third_size_value_after =
        load_bridge_be_u32(base + 0x7001FD3Cu);
    vc_apf_third_boundary_observed.stage = 3u;
    /* Throw unconditionally: 0x84BED80C must not execute in this milestone. */
    stop(gate_status, adapter_status);
}
'''
    derived = derived[:start] + replacement + derived[end:]

    api_marker = (
        "vc_apf_first_entry_status vc_apf_first_entry_xenon_bridge_bind(\n"
    )
    require(derived.count(api_marker) == 1,
            "bridge bind marker changed")
    api = r'''bool vc_apf_third_boundary_mode_arm(
    vc_apf_first_entry_state *state, std::uint64_t nonce) {
    if (state == nullptr || state != vc_apf_bound_state || !state->prepared ||
        !state->generated_dispatch_installed ||
        !vc_apf_guest_instruction_budget_is_bound() ||
        vc_apf_third_boundary_armed || nonce != UINT64_C(0xA2F23008D80880C3)) {
        return false;
    }
    vc_apf_third_boundary_observed =
        vc_apf_third_boundary_bridge_evidence{};
    vc_apf_third_boundary_armed = true;
    return true;
}

void vc_apf_third_boundary_mode_evidence(
    vc_apf_third_boundary_bridge_evidence *evidence) {
    if (evidence != nullptr) {
        *evidence = vc_apf_third_boundary_observed;
    }
}

'''
    derived = derived.replace(api_marker, api + api_marker, 1)
    return derived


def specialized_budget_source(original: str) -> str:
    """Preserve the exact ledger while adding a bounded full-PC observer."""

    require(hashlib.sha256(original.encode("utf-8")).hexdigest() ==
            EXPECTED_BUDGET_SOURCE_SHA256,
            "guest-instruction budget source changed")
    count_marker = (
        "thread_local std::uint32_t vc_apf_recent_guest_address_next = 0u;\n"
    )
    require(original.count(count_marker) == 1,
            "budget trace state marker changed")
    derived = original.replace(
        count_marker,
        count_marker +
        "thread_local std::uint32_t vc_apf_third_boundary_full_trace[4096]{};\n"
        "thread_local std::size_t vc_apf_third_boundary_full_count = 0u;\n",
        1)
    reset_marker = "    vc_apf_recent_guest_address_next = 0u;\n"
    require(derived.count(reset_marker) == 1,
            "budget bind reset marker changed")
    derived = derived.replace(
        reset_marker,
        reset_marker + "    vc_apf_third_boundary_full_count = 0u;\n",
        1)
    record_marker = (
        "    vc_apf_recent_guest_addresses[vc_apf_recent_guest_address_next] =\n"
        "        guest_address;\n"
    )
    require(derived.count(record_marker) == 1,
            "budget successful-step marker changed")
    derived = derived.replace(
        record_marker,
        "    if (vc_apf_third_boundary_full_count < 4096u) {\n"
        "        vc_apf_third_boundary_full_trace[\n"
        "            vc_apf_third_boundary_full_count++] = guest_address;\n"
        "    }\n" + record_marker,
        1)
    derived += r'''

std::size_t vc_apf_third_boundary_full_trace_copy(
    std::uint32_t *addresses, std::size_t capacity) {
    if (addresses == nullptr ||
        capacity < vc_apf_third_boundary_full_count) {
        return 0u;
    }
    for (std::size_t index = 0u;
         index < vc_apf_third_boundary_full_count; ++index) {
        addresses[index] = vc_apf_third_boundary_full_trace[index];
    }
    return vc_apf_third_boundary_full_count;
}
'''
    return derived


def harness_source() -> str:
    return r'''#include "ppc_recomp_shared.h"
#include "nonfrontier_abort.h"
#include "third_boundary_evidence.h"
#include "static_runtime/apf_first_entry_xenon_bridge.h"
#include "static_runtime/apf_guest_instruction_budget.h"

#include <cerrno>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <poll.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <vector>

namespace {

constexpr const char *kAuthorizationToken =
    "apf2k8-v1:d60c0116:1a0b9ac0:981a5714:cde5b922:third-boundary-commit-only";
constexpr std::uint64_t kAuthorizationNonce = UINT64_C(0xA2F23008D80880C3);
constexpr std::uint32_t kMagic = 0x41504634u;
constexpr std::uint32_t kInstructionLimit = 4096u;
constexpr std::uint32_t kFunctionDispatchLimit = 64u;
constexpr std::uint32_t kTraceCapacity = 4096u;
constexpr std::uint32_t kExpectedSecondThunk = 0x84D0863Cu;
constexpr std::uint32_t kExpectedSecondCall = 0x84BED7B8u;
constexpr std::uint32_t kExpectedSecondReturn = 0x84BED7BCu;
constexpr std::uint32_t kExpectedThirdThunk = 0x84D0863Cu;
constexpr std::uint32_t kExpectedThirdCall = 0x84BED808u;
constexpr std::uint32_t kExpectedThirdReturn = 0x84BED80Cu;
constexpr std::uint32_t kBasePointer = 0x7001FC50u;
constexpr std::uint32_t kSizePointer = 0x7001FD34u;
constexpr std::uint32_t kRequestedSize = 0x00100000u;
constexpr std::uint32_t kCommitBasePointer = 0x7001FC54u;
constexpr std::uint32_t kCommitSizePointer = 0x7001FD3Cu;
constexpr std::uint32_t kCommitSize = 0x00010000u;

enum class child_outcome : std::uint32_t {
    expected_third_boundary = 1,
    instruction_budget_exhausted,
    import_abort,
    unexpected_return,
    prerequisite_failure,
    unexpected_exception,
};

struct child_report {
    std::uint32_t magic;
    child_outcome outcome;
    std::uint32_t prerequisite_step;
    std::uint32_t entry_authorized;
    std::uint32_t entry_called;
    std::uint32_t gate_status;
    std::uint32_t adapter_status;
    std::uint32_t import_thunk;
    std::uint32_t import_abort_index;
    std::uint32_t stop_guest_address;
    std::uint32_t last_guest_address;
    std::uint32_t context_lr;
    std::uint32_t context_r3;
    std::uint32_t reserve_base_before;
    std::uint32_t reserve_size_before;
    std::uint32_t reserve_base_after;
    std::uint32_t reserve_size_after;
    std::uint32_t commit_base_before;
    std::uint32_t commit_size_before;
    std::uint32_t commit_base_after;
    std::uint32_t commit_size_after;
    std::uint32_t vm_page_count;
    std::uint32_t vm_allocation_count;
    std::uint32_t reserved_page_count;
    std::uint32_t committed_page_count;
    std::uint32_t vm_ledger_exact;
    std::uint32_t first_page_zeroed;
    std::uint32_t remaining_backing_pattern_exact;
    std::uint64_t backing_fnv_before;
    std::uint64_t backing_fnv_after;
    std::uint64_t instructions_consumed;
    std::uint64_t function_dispatches_consumed;
    vc_apf_third_boundary_bridge_evidence bridge;
    std::uint32_t trace_count;
    std::uint32_t trace[kTraceCapacity];
};

std::vector<std::uint8_t> read_file(const char *path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) return {};
    const std::streamsize size = stream.tellg();
    if (size < 0) return {};
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
    stream.seekg(0);
    if (!stream.read(reinterpret_cast<char *>(bytes.data()), size)) return {};
    return bytes;
}

std::uint32_t load_be_u32(const std::uint8_t *bytes) {
    return (static_cast<std::uint32_t>(bytes[0]) << 24u) |
           (static_cast<std::uint32_t>(bytes[1]) << 16u) |
           (static_cast<std::uint32_t>(bytes[2]) << 8u) |
           static_cast<std::uint32_t>(bytes[3]);
}

std::uint64_t fnv1a64(const std::uint8_t *bytes, std::size_t count) {
    std::uint64_t value = UINT64_C(14695981039346656037);
    for (std::size_t index = 0u; index < count; ++index) {
        value ^= bytes[index];
        value *= UINT64_C(1099511628211);
    }
    return value;
}

std::int64_t monotonic_milliseconds() {
    struct timespec now{};
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return -1;
    return static_cast<std::int64_t>(now.tv_sec) * 1000 +
           now.tv_nsec / 1000000;
}

int containment_normal(void *) { return 0x6B52; }
int containment_signal(void *) {
    std::raise(SIGKILL);
    return 0;
}
int containment_timeout(void *) {
    for (;;) pause();
}

bool containment_self_test() {
    vc_apf_first_entry_child_result result{};
    if (vc_apf_first_entry_run_contained(containment_normal, nullptr, 500u,
                                         &result) != VC_APF_FIRST_ENTRY_OK ||
        result.outcome != VC_APF_FIRST_ENTRY_CHILD_EXITED ||
        result.callback_result != 0x6B52) return false;
    if (vc_apf_first_entry_run_contained(containment_signal, nullptr, 500u,
                                         &result) != VC_APF_FIRST_ENTRY_OK ||
        result.outcome != VC_APF_FIRST_ENTRY_CHILD_SIGNALED ||
        result.signal_number != SIGKILL) return false;
    if (vc_apf_first_entry_run_contained(containment_timeout, nullptr, 100u,
                                         &result) != VC_APF_FIRST_ENTRY_OK ||
        result.outcome != VC_APF_FIRST_ENTRY_CHILD_TIMED_OUT ||
        result.signal_number != SIGKILL) return false;
    return true;
}

void snapshot(child_report &report, vc_apf_first_entry_state &state,
              PPCContext &context) {
    report.instructions_consumed = state.budget.instructions_consumed;
    report.function_dispatches_consumed =
        state.budget.function_dispatches_consumed;
    report.context_lr = static_cast<std::uint32_t>(context.lr);
    report.context_r3 = context.r3.u32;
    report.trace_count = static_cast<std::uint32_t>(
        vc_apf_third_boundary_full_trace_copy(report.trace, kTraceCapacity));
    if (report.trace_count != 0u) {
        report.last_guest_address = report.trace[report.trace_count - 1u];
    }
    vc_apf_third_boundary_mode_evidence(&report.bridge);
}

void write_report_and_exit(int descriptor, const child_report &report) {
    const auto *bytes = reinterpret_cast<const std::uint8_t *>(&report);
    std::size_t written_total = 0u;
    while (written_total < sizeof(report)) {
        const ssize_t written = write(descriptor, bytes + written_total,
                                      sizeof(report) - written_total);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) _exit(120);
        written_total += static_cast<std::size_t>(written);
    }
    close(descriptor);
    _exit(0);
}

bool initial_vm_ledger_exact(const vc_apf_boot_leaf_runtime &runtime) {
    if (runtime.vm_page_count != 4096u ||
        runtime.vm_allocation_count != 0u) return false;
    for (std::size_t index = 0u; index < runtime.vm_page_count; ++index) {
        if (runtime.vm_pages[index].allocation_id != 0u ||
            runtime.vm_pages[index].state != 0u ||
            runtime.vm_pages[index].protect != 0u) return false;
    }
    for (std::size_t index = 0u;
         index < VC_APF_BOOT_VM_MAX_ALLOCATIONS; ++index) {
        if (runtime.vm_allocations[index].active) return false;
    }
    return true;
}

bool final_vm_ledger_exact(const vc_apf_boot_leaf_runtime &runtime,
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
        if (index == 0u) {
            if (page.allocation_id != 1u || page.state != 2u ||
                page.protect != VC_APF_X_PAGE_READWRITE) return false;
            ++committed;
        } else if (index < 16u) {
            if (page.allocation_id != 1u || page.state != 1u ||
                page.protect != VC_APF_X_PAGE_READWRITE) return false;
            ++reserved;
        } else if (page.allocation_id != 0u || page.state != 0u ||
                   page.protect != 0u) {
            return false;
        }
    }
    *reserved_count = reserved;
    *committed_count = committed;
    return reserved == 15u && committed == 1u;
}

[[noreturn]] void execute_child(int descriptor,
                                const std::vector<std::uint8_t> &image,
                                const std::vector<std::uint8_t> &xex) {
    child_report report{};
    report.magic = kMagic;
    report.outcome = child_outcome::prerequisite_failure;
    report.gate_status = VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    report.adapter_status = VC_APF_BOOT_LEAF_INVALID_ARGUMENT;

    vc_apf_first_entry_config config{};
    config.decoded_image_bytes = image.data();
    config.decoded_image_byte_count = image.size();
    config.raw_xex_prefix_bytes = xex.data();
    config.raw_xex_prefix_byte_count = xex.size();
    config.policy.configured_fields = VC_APF_BOOT_CONFIG_ALL;
    config.policy.process_type = 1u;
    config.policy.language = 1u;
    config.policy.av_pack = 6u;
    config.policy.executable_system_flags = 0x00000200u;
    config.policy.secured_av_region = 0u;
    config.policy.user_video_flags = 0u;
    config.policy.vm_arena_base = 0x40000000u;
    config.policy.vm_arena_size = 0x10000000u;
    config.instruction_budget = kInstructionLimit;
    config.function_dispatch_budget = kFunctionDispatchLimit;

    vc_apf_first_entry_state state{};
    PPCContext context{};
    report.prerequisite_step = 1u;
    if (vc_apf_first_entry_prepare(&state, &config) !=
        VC_APF_FIRST_ENTRY_OK) write_report_and_exit(descriptor, report);
    report.prerequisite_step = 2u;
    if (!state.prepared || state.adapter_runtime == nullptr ||
        state.guest_address_space_byte_count !=
            VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE ||
        state.imported_data.seeded_slot_count != 2u ||
        state.imported_data.preserved_ordinal_slot_count != 11u ||
        state.imported_data.raw_xex_prefix != 0x70020100u ||
        !state.imported_data_evidence.sub_84bf1850_reaches_header_query ||
        state.imported_data_evidence.requested_key_present ||
        !state.imported_data_evidence.bounded_absent_key_result_is_null ||
        state.imported_data_evidence.callback_dispatch_possible ||
        state.adapter_runtime->config.vm_arena_base != 0x40000000u ||
        state.adapter_runtime->config.vm_arena_size != 0x10000000u ||
        state.adapter_runtime->config.vm_backing_bytes !=
            state.guest_address_space + 0x40000000u ||
        state.adapter_runtime->config.vm_backing_byte_count != 0x10000000u ||
        !initial_vm_ledger_exact(*state.adapter_runtime)) {
        vc_apf_first_entry_destroy(&state);
        write_report_and_exit(descriptor, report);
    }
    report.prerequisite_step = 3u;
    if (vc_apf_first_entry_xenon_install_dispatch(
            &state, PPCFuncMappings, 60731u) != VC_APF_FIRST_ENTRY_OK ||
        state.generated_dispatch_mapping_count != 60731u ||
        PPC_LOOKUP_FUNC(state.guest_address_space, 0x84BE9D08u) != _xstart ||
        PPC_LOOKUP_FUNC(state.guest_address_space,
                        VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK) !=
            __imp__RtlImageXexHeaderField ||
        PPC_LOOKUP_FUNC(state.guest_address_space, kExpectedSecondThunk) !=
            __imp__NtAllocateVirtualMemory) {
        vc_apf_first_entry_destroy(&state);
        write_report_and_exit(descriptor, report);
    }
    report.prerequisite_step = 4u;
    if (vc_apf_first_entry_xenon_context_init(&context) !=
            VC_APF_FIRST_ENTRY_OK ||
        context.r1.u32 != VC_APF_FIRST_ENTRY_STACK_TOP || context.lr != 0u) {
        vc_apf_first_entry_destroy(&state);
        write_report_and_exit(descriptor, report);
    }
    report.prerequisite_step = 5u;
    if (vc_apf_first_entry_xenon_bridge_bind(&state) !=
            VC_APF_FIRST_ENTRY_OK ||
        vc_apf_guest_instruction_budget_bind(&state.budget) !=
            VC_APF_FIRST_ENTRY_OK ||
        !vc_apf_third_boundary_mode_arm(&state, kAuthorizationNonce)) {
        vc_apf_guest_instruction_budget_unbind();
        vc_apf_first_entry_xenon_bridge_unbind();
        vc_apf_first_entry_destroy(&state);
        write_report_and_exit(descriptor, report);
    }

    std::uint8_t *const vm_backing =
        state.adapter_runtime->config.vm_backing_bytes;
    for (std::uint32_t index = 0u; index < kRequestedSize; ++index) {
        vm_backing[index] = static_cast<std::uint8_t>(
            (index * 131u + 17u) & 0xFFu);
    }
    report.backing_fnv_before = fnv1a64(vm_backing, kRequestedSize);
    report.reserve_base_before =
        load_be_u32(state.guest_address_space + kBasePointer);
    report.reserve_size_before =
        load_be_u32(state.guest_address_space + kSizePointer);

    report.prerequisite_step = 6u;
    report.entry_authorized = 1u;
    report.entry_called = 1u;
    try {
        _xstart(context, state.guest_address_space);
        report.outcome = child_outcome::unexpected_return;
    } catch (const vc_apf_first_entry_boundary_stop &stop) {
        report.gate_status = static_cast<std::uint32_t>(stop.gate_status);
        report.adapter_status = static_cast<std::uint32_t>(stop.adapter_status);
        report.import_thunk = stop.import_thunk;
        report.outcome = stop.import_thunk == kExpectedThirdThunk
                             ? child_outcome::expected_third_boundary
                             : child_outcome::import_abort;
    } catch (const vc_apf_guest_instruction_budget_stop &stop) {
        report.outcome = child_outcome::instruction_budget_exhausted;
        report.gate_status = static_cast<std::uint32_t>(stop.ledger_status);
        report.stop_guest_address = stop.guest_address;
    } catch (const vc_apf_nonfrontier_import_abort &stop) {
        report.outcome = child_outcome::import_abort;
        report.import_abort_index = stop.import_index;
    } catch (...) {
        report.outcome = child_outcome::unexpected_exception;
    }
    snapshot(report, state, context);
    report.reserve_base_before = report.bridge.second_base_value_before;
    report.reserve_size_before = report.bridge.second_size_value_before;
    report.reserve_base_after =
        load_be_u32(state.guest_address_space + kBasePointer);
    report.reserve_size_after =
        load_be_u32(state.guest_address_space + kSizePointer);
    report.commit_base_before = report.bridge.third_base_value_before;
    report.commit_size_before = report.bridge.third_size_value_before;
    report.commit_base_after =
        load_be_u32(state.guest_address_space + kCommitBasePointer);
    report.commit_size_after =
        load_be_u32(state.guest_address_space + kCommitSizePointer);
    report.vm_page_count =
        static_cast<std::uint32_t>(state.adapter_runtime->vm_page_count);
    report.vm_allocation_count = static_cast<std::uint32_t>(
        state.adapter_runtime->vm_allocation_count);
    report.vm_ledger_exact = final_vm_ledger_exact(
        *state.adapter_runtime, &report.reserved_page_count,
        &report.committed_page_count) ? 1u : 0u;
    report.backing_fnv_after = fnv1a64(vm_backing, kRequestedSize);
    report.first_page_zeroed = 1u;
    for (std::uint32_t index = 0u; index < kCommitSize; ++index) {
        if (vm_backing[index] != 0u) {
            report.first_page_zeroed = 0u;
            break;
        }
    }
    report.remaining_backing_pattern_exact = 1u;
    for (std::uint32_t index = kCommitSize;
         index < kRequestedSize; ++index) {
        if (vm_backing[index] != static_cast<std::uint8_t>(
                (index * 131u + 17u) & 0xFFu)) {
            report.remaining_backing_pattern_exact = 0u;
            break;
        }
    }

    const bool expected =
        report.outcome == child_outcome::expected_third_boundary &&
        report.gate_status == VC_APF_FIRST_ENTRY_OK &&
        report.adapter_status == VC_APF_BOOT_LEAF_OK &&
        report.import_thunk == kExpectedThirdThunk &&
        report.instructions_consumed == 283u &&
        report.function_dispatches_consumed == 3u &&
        report.trace_count == 283u &&
        report.last_guest_address == kExpectedThirdCall &&
        report.context_lr == kExpectedThirdReturn &&
        report.context_r3 == VC_APF_X_STATUS_SUCCESS &&
        report.bridge.stage == 3u &&
        report.bridge.first_thunk == VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK &&
        report.bridge.first_lr == VC_APF_FIRST_ENTRY_FIRST_IMPORT_RETURN &&
        report.bridge.first_r3_input == 0x70020100u &&
        report.bridge.first_r4_input ==
            VC_APF_IMPORTED_DATA_XEX_DEFAULT_HEAP_SIZE &&
        report.bridge.first_r3_output == 0u &&
        report.bridge.first_instruction_count == 38u &&
        report.bridge.second_thunk == kExpectedSecondThunk &&
        report.bridge.second_lr == kExpectedSecondReturn &&
        report.bridge.second_r3_input == kBasePointer &&
        report.bridge.second_r4_input == kSizePointer &&
        report.bridge.second_r5_input == 0x60002000u &&
        report.bridge.second_r6_input == VC_APF_X_PAGE_READWRITE &&
        report.bridge.second_r7_input == 0u &&
        report.bridge.second_r3_output == VC_APF_X_STATUS_SUCCESS &&
        report.bridge.second_instruction_count == 264u &&
        report.bridge.reserve_vm_ledger_exact_before_continuation == 1u &&
        report.bridge.reserve_backing_pattern_exact_before_continuation == 1u &&
        report.bridge.reserve_backing_fnv_before_continuation ==
            UINT64_C(0x1F5E0DF9BC822325) &&
        report.bridge.third_thunk == kExpectedThirdThunk &&
        report.bridge.third_lr == kExpectedThirdReturn &&
        report.bridge.third_r3_input == kCommitBasePointer &&
        report.bridge.third_r4_input == kCommitSizePointer &&
        report.bridge.third_r5_input == 0x60001000u &&
        report.bridge.third_r6_input == VC_APF_X_PAGE_READWRITE &&
        report.bridge.third_r7_input == 0u &&
        report.bridge.third_r3_output == VC_APF_X_STATUS_SUCCESS &&
        report.bridge.third_base_value_before == 0x40000000u &&
        report.bridge.third_size_value_before == kCommitSize &&
        report.bridge.third_base_value_after == 0x40000000u &&
        report.bridge.third_size_value_after == kCommitSize &&
        report.bridge.third_instruction_count == 283u &&
        report.reserve_base_before == 0u &&
        report.reserve_size_before == kRequestedSize &&
        report.reserve_base_after == 0x40000000u &&
        report.reserve_size_after == kRequestedSize &&
        report.commit_base_before == 0x40000000u &&
        report.commit_size_before == kCommitSize &&
        report.commit_base_after == 0x40000000u &&
        report.commit_size_after == kCommitSize &&
        report.vm_page_count == 4096u &&
        report.vm_allocation_count == 1u &&
        report.reserved_page_count == 15u &&
        report.committed_page_count == 1u &&
        report.vm_ledger_exact == 1u && report.first_page_zeroed == 1u &&
        report.remaining_backing_pattern_exact == 1u &&
        report.backing_fnv_before == UINT64_C(0x1F5E0DF9BC822325) &&
        report.backing_fnv_after == UINT64_C(0x8179632E8A902325);
    if (report.outcome == child_outcome::expected_third_boundary &&
        !expected) {
        report.outcome = child_outcome::unexpected_exception;
    }

    vc_apf_guest_instruction_budget_unbind();
    vc_apf_first_entry_xenon_bridge_unbind();
    vc_apf_first_entry_destroy(&state);
    write_report_and_exit(descriptor, report);
}

const char *outcome_name(child_outcome outcome) {
    switch (outcome) {
    case child_outcome::expected_third_boundary:
        return "expected_third_boundary";
    case child_outcome::instruction_budget_exhausted:
        return "budget_exhaustion";
    case child_outcome::import_abort: return "import_abort";
    case child_outcome::unexpected_return: return "unexpected_return";
    case child_outcome::prerequisite_failure: return "prerequisite_failure";
    case child_outcome::unexpected_exception: return "unexpected_exception";
    }
    return "unknown";
}

} // namespace

int main(int argc, char **argv) {
    if (argc != 4 || std::strcmp(argv[3], kAuthorizationToken) != 0) return 2;
    const std::vector<std::uint8_t> image = read_file(argv[1]);
    const std::vector<std::uint8_t> xex = read_file(argv[2]);
    if (image.size() != VC_APF_IMPORTED_DATA_IMAGE_SIZE ||
        xex.size() < VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE) return 3;
    if (!containment_self_test()) return 4;

    int descriptors[2];
    if (pipe(descriptors) != 0) return 5;
    const pid_t child = fork();
    if (child < 0) return 6;
    if (child == 0) {
        close(descriptors[0]);
        execute_child(descriptors[1], image, xex);
    }
    close(descriptors[1]);

    child_report report{};
    int wait_status = 0;
    const std::int64_t started = monotonic_milliseconds();
    if (started < 0) return 7;
    bool timed_out = false;
    for (;;) {
        const std::int64_t now = monotonic_milliseconds();
        if (now < 0) return 8;
        const std::int64_t remaining64 = started + 5000 - now;
        if (remaining64 <= 0) {
            timed_out = true;
            kill(child, SIGKILL);
            break;
        }
        struct pollfd descriptor{descriptors[0], POLLIN | POLLHUP, 0};
        const int status = poll(&descriptor, 1u,
                                static_cast<int>(remaining64));
        if (status > 0) break;
        if (status == 0) {
            timed_out = true;
            kill(child, SIGKILL);
            break;
        }
        if (errno != EINTR) return 9;
    }

    std::size_t received = 0u;
    if (!timed_out) {
        auto *bytes = reinterpret_cast<std::uint8_t *>(&report);
        while (received < sizeof(report)) {
            const ssize_t count = read(descriptors[0], bytes + received,
                                       sizeof(report) - received);
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) break;
            received += static_cast<std::size_t>(count);
        }
    }
    close(descriptors[0]);
    while (waitpid(child, &wait_status, 0) < 0 && errno == EINTR) {}

    if (timed_out) {
        std::printf("APF_GUARDED_THIRD_BOUNDARY_CHILD_RESULT outcome=timeout "
                    "signal=%d containment_normal=1 containment_signal=1 "
                    "containment_timeout=1\n", SIGKILL);
        return 20;
    }
    if (WIFSIGNALED(wait_status)) {
        std::printf("APF_GUARDED_THIRD_BOUNDARY_CHILD_RESULT outcome=signal "
                    "signal=%d containment_normal=1 containment_signal=1 "
                    "containment_timeout=1\n", WTERMSIG(wait_status));
        return 21;
    }
    if (!WIFEXITED(wait_status) || WEXITSTATUS(wait_status) != 0 ||
        received != sizeof(report) || report.magic != kMagic) {
        std::printf("APF_GUARDED_THIRD_BOUNDARY_CHILD_RESULT "
                    "outcome=import_abort signal=0 containment_normal=1 "
                    "containment_signal=1 containment_timeout=1 "
                    "report_missing=1\n");
        return 22;
    }

    std::printf(
        "APF_GUARDED_THIRD_BOUNDARY_CHILD_RESULT outcome=%s signal=0 "
        "entry_authorized=%u entry_called=%u prerequisite_step=%u "
        "gate_status=%u adapter_status=%u thunk=0x%08X stage=%u "
        "instructions=%llu function_dispatches=%llu last_pc=0x%08X "
        "lr=0x%08X r3=0x%08X first_instructions=%u "
        "first_thunk=0x%08X first_lr=0x%08X first_r3_in=0x%08X "
        "first_r4_in=0x%08X first_r3_out=0x%08X "
        "second_instructions=%u second_r3_in=0x%08X "
        "second_r4_in=0x%08X second_r5_in=0x%08X "
        "second_r6_in=0x%08X second_r7_in=0x%08X "
        "second_r3_out=0x%08X reserve_ledger_before=%u "
        "reserve_pattern_before=%u reserve_fnv_before=0x%016llX "
        "third_instructions=%u third_r3_in=0x%08X "
        "third_r4_in=0x%08X third_r5_in=0x%08X "
        "third_r6_in=0x%08X third_r7_in=0x%08X "
        "third_r3_out=0x%08X reserve_base_before=0x%08X "
        "reserve_size_before=0x%08X reserve_base_after=0x%08X "
        "reserve_size_after=0x%08X commit_base_before=0x%08X "
        "commit_size_before=0x%08X commit_base_after=0x%08X "
        "commit_size_after=0x%08X vm_pages=%u "
        "vm_allocations=%u reserved_pages=%u committed_pages=%u "
        "ledger_exact=%u first_page_zeroed=%u "
        "remaining_pattern_exact=%u backing_fnv_before=0x%016llX "
        "backing_fnv_after=0x%016llX trace=",
        outcome_name(report.outcome), report.entry_authorized,
        report.entry_called, report.prerequisite_step, report.gate_status,
        report.adapter_status, report.import_thunk, report.bridge.stage,
        static_cast<unsigned long long>(report.instructions_consumed),
        static_cast<unsigned long long>(
            report.function_dispatches_consumed),
        report.last_guest_address, report.context_lr, report.context_r3,
        report.bridge.first_instruction_count, report.bridge.first_thunk,
        report.bridge.first_lr, report.bridge.first_r3_input,
        report.bridge.first_r4_input, report.bridge.first_r3_output,
        report.bridge.second_instruction_count,
        report.bridge.second_r3_input, report.bridge.second_r4_input,
        report.bridge.second_r5_input, report.bridge.second_r6_input,
        report.bridge.second_r7_input, report.bridge.second_r3_output,
        report.bridge.reserve_vm_ledger_exact_before_continuation,
        report.bridge.reserve_backing_pattern_exact_before_continuation,
        static_cast<unsigned long long>(
            report.bridge.reserve_backing_fnv_before_continuation),
        report.bridge.third_instruction_count,
        report.bridge.third_r3_input, report.bridge.third_r4_input,
        report.bridge.third_r5_input, report.bridge.third_r6_input,
        report.bridge.third_r7_input, report.bridge.third_r3_output,
        report.reserve_base_before, report.reserve_size_before,
        report.reserve_base_after, report.reserve_size_after,
        report.commit_base_before, report.commit_size_before,
        report.commit_base_after, report.commit_size_after,
        report.vm_page_count, report.vm_allocation_count,
        report.reserved_page_count, report.committed_page_count,
        report.vm_ledger_exact, report.first_page_zeroed,
        report.remaining_backing_pattern_exact,
        static_cast<unsigned long long>(report.backing_fnv_before),
        static_cast<unsigned long long>(report.backing_fnv_after));
    for (std::uint32_t index = 0u; index < report.trace_count; ++index) {
        std::printf("%s%08X", index == 0u ? "" : ",",
                    report.trace[index]);
    }
    std::printf(" containment_normal=1 containment_signal=1 "
                "containment_timeout=1\n");
    return report.outcome == child_outcome::expected_third_boundary ? 0 : 23;
}
'''


def parse_result_line(line: str) -> dict[str, str]:
    require(line.startswith(RESULT_PREFIX), "third-boundary result prefix changed")
    fields: dict[str, str] = {}
    for token in line[len(RESULT_PREFIX):].split():
        require("=" in token, f"malformed result token: {token}")
        key, value = token.split("=", 1)
        require(key not in fields, f"duplicate result field: {key}")
        fields[key] = value
    return fields


def trace_sha256(trace: list[int]) -> str:
    data = "".join(f"0x{pc:08X}\n" for pc in trace).encode("ascii")
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--composed", type=Path, default=Path(
        "build-static-recomp-apf/ppc-opcode-switch-composed"))
    parser.add_argument("--generated", type=Path, default=Path(
        "build-static-recomp-apf/ppc-opcode-switch-budget-instrumented"))
    parser.add_argument("--composed-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_static_recomp_opcode_switch_composed.json"))
    parser.add_argument("--budget-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_guest_instruction_budget_instrumentation.json"))
    parser.add_argument("--first-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_guarded_first_entry_execution.json"))
    parser.add_argument("--second-static", type=Path, default=Path(
        "reports/static_recomp/apf2k8_second_boundary_static.json"))
    parser.add_argument("--second-execution", type=Path, default=Path(
        "reports/static_recomp/apf2k8_guarded_second_boundary_execution.json"))
    parser.add_argument("--post-reserve-static", type=Path, default=Path(
        "reports/static_recomp/apf2k8_post_reserve_static.json"))
    parser.add_argument("--leaf-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_boot_leaf_adapters.json"))
    parser.add_argument("--xex-report", type=Path, default=Path(
        "reports/headers/apf2k8_xex_report.json"))
    parser.add_argument("--xex", type=Path, default=Path(
        "extracted/All-Pro Football 2K8 (USA)/default.xex"))
    parser.add_argument("--volume", type=Path, default=Path(
        "extracted/All-Pro Football 2K8 (USA)/0A"))
    parser.add_argument("--decoded", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--temp-root", type=Path,
                        default=Path("/media/noah/Storage/.codex-tmp"))
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--clangxx", default="clang++-18")
    parser.add_argument("--jobs", type=int,
                        default=min(12, os.cpu_count() or 1))
    args = parser.parse_args()

    root = args.root.resolve()
    resolve = lambda path: path.resolve() if path.is_absolute() else \
        (root / path).resolve()
    composed = resolve(args.composed)
    generated = resolve(args.generated)
    composed_report_path = resolve(args.composed_report)
    budget_report_path = resolve(args.budget_report)
    first_report_path = resolve(args.first_report)
    second_static_path = resolve(args.second_static)
    second_execution_path = resolve(args.second_execution)
    post_reserve_static_path = resolve(args.post_reserve_static)
    leaf_report_path = resolve(args.leaf_report)
    xex_report_path = resolve(args.xex_report)
    xex = resolve(args.xex)
    volume = resolve(args.volume)
    decoded = resolve(args.decoded)
    output_json = resolve(args.json)
    transcript = resolve(args.transcript)
    temp_root = resolve(args.temp_root)
    clang = shutil.which(args.clang)
    clangxx = shutil.which(args.clangxx)
    require(args.jobs > 0 and clang is not None and clangxx is not None,
            "pinned Clang toolchain or positive job count is unavailable")

    first_bridge_path = root / "src/static_runtime/apf_first_entry_xenon_bridge.cpp"
    budget_source_path = root / "src/static_runtime/apf_guest_instruction_budget.cpp"
    first_driver_path = root / "tools/apf_guarded_first_entry_execute.py"
    second_driver_path = root / "tools/apf_guarded_second_boundary_execute.py"
    post_reserve_analyzer_path = root / "tools/apf_post_reserve_static.py"
    required_files = [
        composed_report_path, budget_report_path, first_report_path,
        second_static_path, second_execution_path, post_reserve_static_path,
        leaf_report_path, xex_report_path, xex, volume, decoded,
        first_bridge_path, budget_source_path, first_driver_path,
        second_driver_path, post_reserve_analyzer_path,
        root / "include/static_runtime/apf_first_entry_gate.h",
        root / "include/static_runtime/apf_first_entry_xenon_bridge.h",
        root / "include/static_runtime/apf_guest_instruction_budget.h",
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "src/static_runtime/apf_boot_leaf_adapters.c",
    ]
    require(all(path.is_file() and not path.is_symlink()
                for path in required_files),
            "third-boundary input is missing or is a symlink")
    require(sha256_file(xex) == EXPECTED_XEX_SHA256,
            "retail APF XEX hash changed")
    require(sha256_file(volume) == EXPECTED_VOLUME_SHA256,
            "retail APF volume hash changed")
    require(decoded.stat().st_size == EXPECTED_DECODED_SIZE and
            sha256_file(decoded) == EXPECTED_DECODED_SHA256,
            "decoded APF image is not exact")
    require(sha256_file(composed_report_path) ==
            EXPECTED_COMPOSED_REPORT_SHA256,
            "composed-corpus report hash changed")
    require(sha256_file(budget_report_path) == EXPECTED_BUDGET_REPORT_SHA256,
            "instruction-budget report hash changed")
    require(sha256_file(first_report_path) == EXPECTED_FIRST_REPORT_SHA256,
            "v2 first-boundary execution report hash changed")
    require(sha256_file(second_static_path) == EXPECTED_SECOND_STATIC_SHA256,
            "second-boundary static report hash changed")
    require(sha256_file(second_execution_path) ==
            EXPECTED_SECOND_EXECUTION_SHA256,
            "guarded second-boundary report hash changed")
    require(sha256_file(post_reserve_static_path) ==
            EXPECTED_POST_RESERVE_STATIC_SHA256,
            "post-reserve static report hash changed")
    require(sha256_file(leaf_report_path) == EXPECTED_LEAF_REPORT_SHA256,
            "typed leaf-adapter report hash changed")
    require(sha256_file(first_bridge_path) == EXPECTED_FIRST_BRIDGE_SHA256,
            "first-boundary Xenon bridge hash changed")
    require(sha256_file(budget_source_path) == EXPECTED_BUDGET_SOURCE_SHA256,
            "instruction-budget runtime hash changed")
    require(sha256_file(first_driver_path) == EXPECTED_FIRST_DRIVER_SHA256,
            "v2 first-boundary driver hash changed")
    require(sha256_file(second_driver_path) == EXPECTED_SECOND_DRIVER_SHA256,
            "guarded second-boundary driver hash changed")
    require(sha256_file(post_reserve_analyzer_path) ==
            EXPECTED_POST_RESERVE_ANALYZER_SHA256,
            "post-reserve analyzer hash changed")

    composed_report = json.loads(
        composed_report_path.read_text(encoding="utf-8"))
    budget_report = json.loads(budget_report_path.read_text(encoding="utf-8"))
    first_report = json.loads(first_report_path.read_text(encoding="utf-8"))
    second_static = json.loads(second_static_path.read_text(encoding="utf-8"))
    second_execution = json.loads(
        second_execution_path.read_text(encoding="utf-8"))
    post_reserve_static = json.loads(
        post_reserve_static_path.read_text(encoding="utf-8"))
    leaf_report = json.loads(leaf_report_path.read_text(encoding="utf-8"))
    require(first_report["schema"] ==
            "apf2k8_guarded_first_entry_execution/v2" and
            first_report["result"]["child_outcome"] ==
            "expected_typed_boundary" and
            first_report["result"]["expected_first_typed_boundary_reached"]
            is True and
            first_report["result"]["continued_past_first_typed_boundary"]
            is False and
            first_report["generated_execution"][
                "executed_guest_instruction_count"] == 38 and
            first_report["generated_execution"]["first_import_call"] ==
            "0x84BF1888" and
            first_report["generated_execution"]["first_import_return"] ==
            "0x84BF188C" and
            first_report["generated_execution"]["adapter_return_value_r3"] ==
            "0x00000000",
            "v2 first-boundary execution semantics changed")
    require(second_static["schema"] == "apf2k8_second_boundary_static/v1" and
            second_static["start_state"]["pc"] == "0x84BF188C" and
            second_static["start_state"]["r3"] == "0x00000000" and
            second_static["static_trace"][
                "continuation_instruction_count_through_next_call"] == 226 and
            second_static["static_trace"][
                "cumulative_instruction_count_through_next_call"] == 264 and
            second_static["static_trace"]["ordered_pc_sha256"] ==
            EXPECTED_CONTINUATION_TRACE_SHA256 and
            second_static["next_boundary"]["name"] ==
            "NtAllocateVirtualMemory" and
            second_static["next_boundary"]["call_pc"] == "0x84BED7B8" and
            second_static["next_boundary"]["return_pc"] == "0x84BED7BC" and
            second_static["next_boundary"]["thunk"] == "0x84D0863C" and
            second_static["next_boundary"]["arguments"] == {
                "base_value_be_u32": "0x00000000",
                "r3_base_pointer": "0x7001FC50",
                "r4_size_pointer": "0x7001FD34",
                "r5_allocation_type": "0x60002000",
                "r6_protection": "0x00000004",
                "r7_debug_memory": "0x00000000",
                "size_value_be_u32": "0x00100000",
            },
            "static second-boundary semantics changed")
    require(second_execution["schema"] ==
            "apf2k8_guarded_second_boundary_execution/v1" and
            second_execution["result"]["child_outcome"] ==
            "expected_second_boundary" and
            second_execution["result"][
                "second_typed_adapter_completed"] is True and
            second_execution["result"][
                "continued_past_second_typed_boundary"] is False and
            second_execution["generated_execution"][
                "executed_guest_instruction_count"] == 264 and
            second_execution["generated_execution"][
                "function_dispatch_count"] == 2 and
            second_execution["generated_execution"][
                "last_executed_guest_pc"] == "0x84BED7B8" and
            second_execution["generated_execution"]["second_boundary"][
                "ntstatus_r3"] == "0x00000000" and
            second_execution["virtual_memory_ledger"] == {
                "active_allocation_count": 1,
                "allocation_base_page": 0,
                "allocation_page_count": 16,
                "allocation_protection": "0x00000004",
                "allocation_slot": 0,
                "allocation_state": "reserve",
                "arena_base": "0x40000000",
                "arena_size": "0x10000000",
                "backing_fnv1a64_after": "0x1F5E0DF9BC822325",
                "backing_fnv1a64_before": "0x1F5E0DF9BC822325",
                "backing_pattern_byte_exact_unchanged": True,
                "page_count": 4096,
                "page_size": "0x00010000",
                "remaining_allocation_slots_inactive": True,
                "remaining_pages_free": True,
            },
            "guarded second-boundary execution semantics changed")
    require(post_reserve_static["schema"] ==
            "apf2k8_post_reserve_static/v1" and
            post_reserve_static["start_checkpoint"]["pc"] ==
            "0x84BED7BC" and
            post_reserve_static["start_checkpoint"]["lr"] ==
            "0x84BED7BC" and
            post_reserve_static["start_checkpoint"][
                "prior_executed_guest_instructions"] == 264 and
            post_reserve_static["static_trace"][
                "continuation_instruction_count_through_next_call"] == 19 and
            post_reserve_static["static_trace"][
                "cumulative_instruction_count_through_next_call"] == 283 and
            post_reserve_static["static_trace"]["ordered_pc_sha256"] ==
            EXPECTED_POST_RESERVE_TRACE_SHA256 and
            post_reserve_static["next_boundary"]["name"] ==
            "NtAllocateVirtualMemory" and
            post_reserve_static["next_boundary"]["call_pc"] ==
            "0x84BED808" and
            post_reserve_static["next_boundary"]["return_pc"] ==
            "0x84BED80C" and
            post_reserve_static["next_boundary"]["thunk"] ==
            "0x84D0863C" and
            post_reserve_static["next_boundary"]["arguments"] == {
                "base_value_be_u32": "0x40000000",
                "r3_base_pointer": "0x7001FC54",
                "r4_size_pointer": "0x7001FD3C",
                "r5_allocation_type": "0x60001000",
                "r6_protection": "0x00000004",
                "r7_debug_memory": "0x00000000",
                "size_value_be_u32": "0x00010000",
            },
            "post-reserve static semantics changed")
    reserve_rows = [
        item for item in leaf_report["virtual_memory"]["allocate_call_sites"]
        if item["call_address"] == "0x84BED7B8"
    ]
    require(len(reserve_rows) == 1 and
            reserve_rows[0]["return_address"] == "0x84BED7BC" and
            reserve_rows[0]["operation"] == "reserve" and
            reserve_rows[0]["allocation_types"] == ["0x60002000"],
            "exact typed VM adapter evidence changed")
    commit_rows = [
        item for item in leaf_report["virtual_memory"]["allocate_call_sites"]
        if item["call_address"] == "0x84BED808"
    ]
    require(len(commit_rows) == 1 and
            commit_rows[0]["return_address"] == "0x84BED80C" and
            commit_rows[0]["operation"] == "commit" and
            commit_rows[0]["allocation_types"] == ["0x60001000"],
            "exact typed VM commit adapter evidence changed")
    for item in first_report["inputs"]["local_files"]:
        path = root / item["path"]
        require(path.is_file() and not path.is_symlink() and
                path.stat().st_size == item["size"] and
                sha256_file(path) == item["sha256"],
                f"v2 first-boundary pinned file changed: {item['path']}")

    require(composed_report["schema"] ==
            "apf2k8_static_recomp_opcode_switch_composed/v1" and
            composed_report["result"][
                "composed_derived_corpus_blocker_resolved"] is True and
            composed_report["result"]["unrecognized_instruction_count"] == 0 and
            composed_report["generated_corpus"][
                "generated_implementation_count"] ==
            EXPECTED_IMPLEMENTATION_COUNT and
            composed_report["generated_corpus"][
                "cpp_translation_unit_count"] == EXPECTED_CPP_COUNT,
            "composed-corpus gate changed")
    require(budget_report["schema"] ==
            "apf2k8_guest_instruction_budget_instrumentation/v1" and
            budget_report["result"][
                "instruction_budget_blocker_resolved_for_derived_corpus"]
            is True and
            budget_report["result"]["instrumented_hook_count"] ==
            EXPECTED_HOOK_COUNT and
            budget_report["result"]["uninstrumentable_construct_count"] == 0,
            "instruction-budget gate changed")

    composed_roster = first.exact_roster(composed)
    generated_roster = first.exact_roster(generated)
    declared_files = {
        item["name"]: item
        for item in composed_report["generated_corpus"]["files"]
    }
    require(len(declared_files) == len(composed_roster) == 240,
            "composed corpus manifest count changed")
    for path in composed_roster:
        item = declared_files.get(path.name)
        require(item is not None and item["size"] == path.stat().st_size and
                item["sha256"] == sha256_file(path),
                f"composed file mismatch: {path.name}")
    composed_tree = first.composed_tree_sha256(composed_roster)
    instrumented_tree = first.budget_tree_sha256(generated, generated_roster)
    require(composed_tree == EXPECTED_COMPOSED_TREE_SHA256 ==
            composed_report["generated_corpus"]["tree_sha256"],
            "composed tree hash changed")
    require(instrumented_tree == EXPECTED_INSTRUMENTED_TREE_SHA256 ==
            budget_report["output"]["tree_sha256"],
            "instrumented tree hash changed")
    budget_rows = {item["path"]: item for item in budget_report["files"]}
    numbered = [generated / f"ppc_recomp.{index}.cpp"
                for index in range(EXPECTED_NUMBERED_COUNT)]
    require(len(budget_rows) == EXPECTED_NUMBERED_COUNT,
            "budget TU manifest count changed")
    for path in numbered:
        require(budget_rows[path.name]["instrumented_sha256"] ==
                sha256_file(path),
                f"instrumented TU changed: {path.name}")
    require(budget_report["coverage_proof"]["hook_manifest_sha256"] ==
            EXPECTED_HOOK_MANIFEST_SHA256 and
            budget_report["coverage_proof"]["marker_manifest_sha256"] ==
            EXPECTED_HOOK_MANIFEST_SHA256,
            "instruction hook manifest changed")
    hook_count = sum(path.read_text(encoding="utf-8").count(
        "VC_APF_GUEST_INSTRUCTION_STEP(") for path in numbered)
    require(hook_count == EXPECTED_HOOK_COUNT,
            "instrumented hook count changed")
    mapping_text = (generated / "ppc_func_mapping.cpp").read_text(
        encoding="utf-8")
    mapping_count = len(re.findall(
        r"^\s*\{ 0x[0-9A-F]+, [A-Za-z_][A-Za-z0-9_]* \},$",
        mapping_text, re.MULTILINE))
    require(mapping_count == EXPECTED_MAPPING_COUNT and
            "\t{ 0x84BE9D08, _xstart }," in mapping_text,
            "generated mapping/entry changed")

    xex_report = json.loads(xex_report_path.read_text(encoding="utf-8"))
    all_imports = {
        "__imp__" + item["name"] for item in xex_report["imports"]["items"]
        if item["thunk_address"] is not None
    }
    original_bridge_text = first_bridge_path.read_text(encoding="utf-8")
    typed_imports = set(re.findall(
        r"^VC_APF_DEFINE_IMPORT\((__imp__[A-Za-z0-9_]+),",
        original_bridge_text, re.MULTILINE))
    require(len(all_imports) == EXPECTED_IMPORT_COUNT and
            len(typed_imports) == EXPECTED_TYPED_IMPORT_COUNT and
            typed_imports < all_imports,
            "typed/nonfrontier import split changed")
    nonfrontier_imports = sorted(all_imports - typed_imports)

    special_bridge = specialized_bridge_source(original_bridge_text)
    special_budget = specialized_budget_source(
        budget_source_path.read_text(encoding="utf-8"))
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apf-third-boundary-v1-",
                                     dir=temp_root) as temporary:
        build = Path(temporary)
        abort_header = build / "nonfrontier_abort.h"
        stubs = build / "nonfrontier_imports.cpp"
        evidence_header = build / "third_boundary_evidence.h"
        bridge_source = build / "third_boundary_bridge.cpp"
        budget_source = build / "third_boundary_budget.cpp"
        harness = build / "guarded_third_driver.cpp"
        abort_header.write_text(first.nonfrontier_header_source(),
                                encoding="utf-8")
        stubs.write_text(first.nonfrontier_stub_source(nonfrontier_imports),
                         encoding="utf-8")
        evidence_header.write_text(evidence_header_source(), encoding="utf-8")
        bridge_source.write_text(special_bridge, encoding="utf-8")
        budget_source.write_text(special_budget, encoding="utf-8")
        harness.write_text(harness_source(), encoding="utf-8")

        generated_sources = [generated / "ppc_func_mapping.cpp", *numbered]
        cpp_sources = [
            *generated_sources, bridge_source, budget_source, stubs, harness,
        ]
        c_sources = [
            root / "src/static_runtime/apf_first_entry_gate.c",
            root / "src/static_runtime/apf_imported_data_bootstrap.c",
            root / "src/static_runtime/apf_boot_leaf_adapters.c",
        ]
        include_paths = [
            root / "include", generated, build,
            root / "tools/vendor/XenonRecomp/XenonUtils",
            root / "tools/vendor/XenonRecomp/thirdparty/simde",
        ]
        compile_specs: list[tuple[list[str], Path]] = []
        for index, source in enumerate(cpp_sources):
            output = build / f"cpp-{index:03d}.o"
            command = [clangxx, "-std=c++20", "-O0", "-c", str(source),
                       "-o", str(output)]
            command.extend(f"-I{path}" for path in include_paths)
            compile_specs.append((command, output))
        for index, source in enumerate(c_sources):
            output = build / f"c-{index:03d}.o"
            command = [clang, "-std=c11", "-O0", "-D_GNU_SOURCE", "-c",
                       str(source), "-o", str(output),
                       f"-I{root / 'include'}"]
            compile_specs.append((command, output))

        outcomes: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(first.compile_one, command, output): output
                for command, output in compile_specs
            }
            for future in as_completed(futures):
                outcomes.append(future.result())
        failures = [item for item in outcomes if item["return_code"] != 0]
        require(not failures, "third-boundary compilation failed: " +
                " | ".join(item["stderr"][-1800:]
                           for item in failures[:3]))
        require(all(item["output"].is_file() for item in outcomes),
                "third-boundary object is missing")

        executable = build / "apf_guarded_third_boundary_v1"
        objects = [output for _, output in compile_specs]
        linked = subprocess.run([
            clangxx, "-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie",
            *map(str, objects), "-lm", "-o", str(executable),
        ], capture_output=True, text=True, check=False)
        require(linked.returncode == 0,
                "third-boundary runtime link failed: " +
                linked.stderr[-2400:])
        executed = subprocess.run([
            str(executable), str(decoded), str(xex), AUTHORIZATION_TOKEN,
        ], capture_output=True, text=True, check=False, timeout=30)
        require(executed.returncode == 0,
                f"third-boundary child terminal changed ({executed.returncode}): "
                f"{executed.stdout[-4000:]} {executed.stderr[-2400:]}")
        lines = [line for line in executed.stdout.splitlines()
                 if line.startswith(RESULT_PREFIX)]
        require(len(lines) == 1 and executed.stderr == "",
                "third-boundary child transcript changed")
        result_line = lines[0]
        fields = parse_result_line(result_line)

    exact_fields = {
        "outcome": "expected_third_boundary",
        "signal": "0",
        "entry_authorized": "1",
        "entry_called": "1",
        "prerequisite_step": "6",
        "gate_status": "0",
        "adapter_status": "0",
        "stage": "3",
        "instructions": "283",
        "function_dispatches": "3",
        "first_instructions": "38",
        "second_instructions": "264",
        "third_instructions": "283",
        "reserve_ledger_before": "1",
        "reserve_pattern_before": "1",
        "ledger_exact": "1",
        "first_page_zeroed": "1",
        "remaining_pattern_exact": "1",
        "containment_normal": "1",
        "containment_signal": "1",
        "containment_timeout": "1",
    }
    require(all(fields.get(key) == value
                for key, value in exact_fields.items()),
            "third-boundary result scalar changed")
    expected_hex = {
        "thunk": EXPECTED_THIRD_THUNK,
        "last_pc": EXPECTED_THIRD_CALL,
        "lr": EXPECTED_THIRD_RETURN,
        "r3": 0,
        "first_thunk": EXPECTED_FIRST_THUNK,
        "first_lr": EXPECTED_FIRST_RETURN,
        "first_r3_in": 0x70020100,
        "first_r4_in": 0x00020401,
        "first_r3_out": 0,
        "second_r3_in": EXPECTED_BASE_POINTER,
        "second_r4_in": EXPECTED_SIZE_POINTER,
        "second_r5_in": EXPECTED_ALLOCATION_TYPE,
        "second_r6_in": EXPECTED_PROTECT,
        "second_r7_in": 0,
        "second_r3_out": 0,
        "reserve_base_before": 0,
        "reserve_size_before": EXPECTED_REQUESTED_SIZE,
        "reserve_base_after": EXPECTED_ALLOCATED_BASE,
        "reserve_size_after": EXPECTED_REQUESTED_SIZE,
        "third_r3_in": EXPECTED_COMMIT_BASE_POINTER,
        "third_r4_in": EXPECTED_COMMIT_SIZE_POINTER,
        "third_r5_in": EXPECTED_COMMIT_ALLOCATION_TYPE,
        "third_r6_in": EXPECTED_PROTECT,
        "third_r7_in": 0,
        "third_r3_out": 0,
        "commit_base_before": EXPECTED_ALLOCATED_BASE,
        "commit_size_before": EXPECTED_COMMIT_SIZE,
        "commit_base_after": EXPECTED_ALLOCATED_BASE,
        "commit_size_after": EXPECTED_COMMIT_SIZE,
    }
    require(all(int(fields.get(key, "-1"), 0) == value
                for key, value in expected_hex.items()),
            "third-boundary ABI/result changed")
    require(fields.get("vm_pages") == str(EXPECTED_VM_PAGE_COUNT) and
            fields.get("vm_allocations") == "1" and
            fields.get("reserved_pages") ==
            str(EXPECTED_RESERVED_PAGES - EXPECTED_COMMITTED_PAGES) and
            fields.get("committed_pages") ==
            str(EXPECTED_COMMITTED_PAGES) and
            int(fields.get("reserve_fnv_before", "-1"), 0) ==
            EXPECTED_BACKING_FNV_BEFORE and
            int(fields.get("backing_fnv_before", "-1"), 0) ==
            EXPECTED_BACKING_FNV_BEFORE and
            int(fields.get("backing_fnv_after", "-1"), 0) ==
            EXPECTED_BACKING_FNV_AFTER,
            "third-boundary VM ledger/backing result changed")

    trace = [int(value, 16) for value in fields["trace"].split(",") if value]
    require(len(trace) == EXPECTED_THIRD_CUMULATIVE_INSTRUCTIONS and
            trace[EXPECTED_FIRST_INSTRUCTIONS - 1] == EXPECTED_FIRST_CALL and
            trace[EXPECTED_FIRST_INSTRUCTIONS] == EXPECTED_FIRST_RETURN and
            trace[EXPECTED_CUMULATIVE_INSTRUCTIONS - 1] ==
            EXPECTED_SECOND_CALL and
            trace[EXPECTED_CUMULATIVE_INSTRUCTIONS] ==
            EXPECTED_SECOND_RETURN and
            trace[-1] == EXPECTED_THIRD_CALL,
            "dynamic full-PC trace endpoints changed")
    continuation_trace = trace[
        EXPECTED_FIRST_INSTRUCTIONS:EXPECTED_CUMULATIVE_INSTRUCTIONS]
    post_reserve_trace = trace[EXPECTED_CUMULATIVE_INSTRUCTIONS:]
    continuation_sha = trace_sha256(continuation_trace)
    post_reserve_sha = trace_sha256(post_reserve_trace)
    full_trace_sha = trace_sha256(trace)
    first_trace_sha = trace_sha256(trace[:EXPECTED_FIRST_INSTRUCTIONS])
    require(len(continuation_trace) == EXPECTED_CONTINUATION_INSTRUCTIONS and
            continuation_sha == EXPECTED_CONTINUATION_TRACE_SHA256 ==
            second_static["static_trace"]["ordered_pc_sha256"],
            "dynamic continuation trace differs from static proof")
    require(len(post_reserve_trace) == EXPECTED_POST_RESERVE_INSTRUCTIONS and
            post_reserve_sha == EXPECTED_POST_RESERVE_TRACE_SHA256 ==
            post_reserve_static["static_trace"]["ordered_pc_sha256"],
            "dynamic post-reserve trace differs from static proof")

    local_files = [
        root / "include/static_runtime/apf_first_entry_gate.h",
        root / "include/static_runtime/apf_first_entry_xenon_bridge.h",
        root / "include/static_runtime/apf_guest_instruction_budget.h",
        root / "src/static_runtime/apf_first_entry_gate.c",
        first_bridge_path,
        budget_source_path,
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "src/static_runtime/apf_boot_leaf_adapters.c",
        first_driver_path,
        root / "tools/apf_second_boundary_static.py",
        second_driver_path,
        post_reserve_analyzer_path,
        root / "tools/apf_guarded_third_boundary_execute.py",
    ]
    report = {
        "schema": SCHEMA,
        "result": {
            "v2_first_boundary_execution_revalidated": True,
            "static_second_boundary_proof_revalidated": True,
            "guarded_second_boundary_execution_revalidated": True,
            "post_reserve_static_proof_revalidated": True,
            "entry_call_authorized_in_isolated_child": True,
            "entry_called_in_isolated_child": True,
            "translated_title_code_executed": True,
            "first_typed_boundary_returned_under_exact_mode": True,
            "continued_past_first_typed_boundary": True,
            "expected_second_typed_boundary_reached": True,
            "second_typed_adapter_completed": True,
            "continued_past_second_typed_boundary": True,
            "expected_third_typed_boundary_reached": True,
            "third_typed_adapter_completed": True,
            "continued_past_third_typed_boundary": False,
            "child_outcome": fields["outcome"],
            "signal_number": 0,
            "native_boot_proved": False,
            "main_menu_proved": False,
        },
        "authorization_gates": {
            "retail_xex_sha256_exact": True,
            "retail_volume_sha256_exact": True,
            "decoded_image_sha256_and_size_exact": True,
            "v2_first_boundary_report_exact": True,
            "second_boundary_static_report_exact": True,
            "guarded_second_boundary_report_exact": True,
            "post_reserve_static_report_exact": True,
            "typed_leaf_adapter_report_exact": True,
            "composed_report_and_complete_tree_exact": True,
            "instrumentation_report_and_complete_tree_exact": True,
            "all_instruction_hooks_recounted": hook_count,
            "dispatch_mapping_count_revalidated": mapping_count,
            "typed_bridge_binding_count_revalidated": len(typed_imports),
            "first_return_mode_token_required": True,
            "first_return_dynamic_pc_lr_abi_gate": True,
            "second_adapter_dynamic_pc_lr_abi_gate": True,
            "reserve_vm_ledger_exact_before_continuation": True,
            "reserve_backing_pattern_exact_before_continuation": True,
            "third_adapter_dynamic_pc_lr_abi_gate": True,
            "child_containment_normal_revalidated": True,
            "child_containment_signal_revalidated": True,
            "child_containment_timeout_revalidated": True,
            "instruction_limit": INSTRUCTION_LIMIT,
            "function_dispatch_limit": FUNCTION_DISPATCH_LIMIT,
            "timeout_milliseconds": 5000,
        },
        "generated_execution": {
            "entry": f"0x{EXPECTED_ENTRY:08X}",
            "executed_guest_instruction_count": len(trace),
            "function_dispatch_count": int(fields["function_dispatches"]),
            "last_executed_guest_pc": f"0x{trace[-1]:08X}",
            "full_ordered_pc_sha256": full_trace_sha,
            "first_boundary_ordered_pc_sha256": first_trace_sha,
            "continuation_ordered_pc_sha256": continuation_sha,
            "post_reserve_ordered_pc_sha256": post_reserve_sha,
            "ordered_guest_pcs": [f"0x{pc:08X}" for pc in trace],
            "first_boundary": {
                "import": "RtlImageXexHeaderField",
                "call_pc": f"0x{EXPECTED_FIRST_CALL:08X}",
                "return_pc": f"0x{EXPECTED_FIRST_RETURN:08X}",
                "thunk": f"0x{EXPECTED_FIRST_THUNK:08X}",
                "instruction_count_at_call": EXPECTED_FIRST_INSTRUCTIONS,
                "r3_header": fields["first_r3_in"],
                "r4_key": fields["first_r4_in"],
                "r3_result": fields["first_r3_out"],
                "returned_to_generated_code": True,
                "authorization_mode": "token+stage+dynamic-PC+LR+exact-ABI",
            },
            "second_boundary": {
                "import": "NtAllocateVirtualMemory",
                "call_pc": f"0x{EXPECTED_SECOND_CALL:08X}",
                "return_pc": f"0x{EXPECTED_SECOND_RETURN:08X}",
                "thunk": f"0x{EXPECTED_SECOND_THUNK:08X}",
                "instruction_count_at_call": EXPECTED_CUMULATIVE_INSTRUCTIONS,
                "arguments": {
                    "r3_base_pointer": fields["second_r3_in"],
                    "base_value_before_be_u32":
                        fields["reserve_base_before"],
                    "r4_size_pointer": fields["second_r4_in"],
                    "size_value_before_be_u32":
                        fields["reserve_size_before"],
                    "r5_allocation_type": fields["second_r5_in"],
                    "r6_protection": fields["second_r6_in"],
                    "r7_debug_memory": fields["second_r7_in"],
                },
                "adapter_status": "ok",
                "ntstatus_r3": fields["second_r3_out"],
                "base_value_after_be_u32": fields["reserve_base_after"],
                "size_value_after_be_u32": fields["reserve_size_after"],
                "reserve_vm_ledger_exact_before_continuation": True,
                "reserve_backing_pattern_exact_before_continuation": True,
                "reserve_backing_fnv1a64_before_continuation":
                    fields["reserve_fnv_before"],
                "generated_return_instruction_executed": True,
                "terminal_semantics": (
                    "existing typed reserve adapter completed; exact VM and "
                    "backing gates authorized 0x84BED7BC"
                ),
            },
            "third_boundary": {
                "import": "NtAllocateVirtualMemory",
                "call_pc": f"0x{EXPECTED_THIRD_CALL:08X}",
                "return_pc": f"0x{EXPECTED_THIRD_RETURN:08X}",
                "thunk": f"0x{EXPECTED_THIRD_THUNK:08X}",
                "instruction_count_at_call":
                    EXPECTED_THIRD_CUMULATIVE_INSTRUCTIONS,
                "arguments": {
                    "r3_base_pointer": fields["third_r3_in"],
                    "base_value_before_be_u32":
                        fields["commit_base_before"],
                    "r4_size_pointer": fields["third_r4_in"],
                    "size_value_before_be_u32":
                        fields["commit_size_before"],
                    "r5_allocation_type": fields["third_r5_in"],
                    "r6_protection": fields["third_r6_in"],
                    "r7_debug_memory": fields["third_r7_in"],
                },
                "adapter_status": "ok",
                "ntstatus_r3": fields["third_r3_out"],
                "base_value_after_be_u32": fields["commit_base_after"],
                "size_value_after_be_u32": fields["commit_size_after"],
                "generated_return_instruction_executed": False,
                "terminal_semantics": (
                    "existing typed commit adapter completed; bridge threw "
                    "before the generated instruction at 0x84BED80C"
                ),
            },
        },
        "virtual_memory_ledger": {
            "arena_base": "0x40000000",
            "arena_size": "0x10000000",
            "page_size": "0x00010000",
            "page_count": int(fields["vm_pages"]),
            "active_allocation_count": int(fields["vm_allocations"]),
            "allocation_slot": 0,
            "allocation_base_page": 0,
            "allocation_page_count": EXPECTED_RESERVED_PAGES,
            "committed_page_count": int(fields["committed_pages"]),
            "remaining_reserved_page_count": int(fields["reserved_pages"]),
            "first_page_state": "commit",
            "remaining_allocation_page_state": "reserve",
            "allocation_protection": "0x00000004",
            "remaining_pages_free": True,
            "remaining_allocation_slots_inactive": True,
            "first_page_backing_zeroed": True,
            "remaining_allocation_backing_pattern_exact": True,
            "backing_fnv1a64_before": fields["backing_fnv_before"],
            "backing_fnv1a64_after": fields["backing_fnv_after"],
        },
        "outcome_classification": {
            "implemented": [
                "expected_third_boundary", "budget_exhaustion",
                "import_abort", "signal", "timeout", "unexpected_return",
                "prerequisite_failure", "unexpected_exception",
            ],
            "observed": "expected_third_boundary",
        },
        "inputs": {
            "retail_xex": pin(xex, root),
            "retail_volume": pin(volume, root),
            "decoded_image": {
                "size": decoded.stat().st_size,
                "sha256": sha256_file(decoded),
                "temporary_validator_artifact": True,
            },
            "v2_first_boundary_report": pin(first_report_path, root),
            "second_boundary_static_report": pin(second_static_path, root),
            "guarded_second_boundary_report":
                pin(second_execution_path, root),
            "post_reserve_static_report":
                pin(post_reserve_static_path, root),
            "typed_leaf_adapter_report": pin(leaf_report_path, root),
            "composed_report": pin(composed_report_path, root),
            "budget_report": pin(budget_report_path, root),
            "composed_corpus": {
                "path": relative(composed, root),
                "file_count": len(composed_roster),
                "tree_sha256": composed_tree,
            },
            "instrumented_corpus": {
                "path": relative(generated, root),
                "file_count": len(generated_roster),
                "tree_sha256": instrumented_tree,
            },
            "local_files": [pin(path, root) for path in local_files],
        },
        "isolation": {
            "normal_host_shell_linked": False,
            "normal_host_shell_modified": False,
            "retail_inputs_modified": False,
            "guest_execution_process": "forked bounded child",
            "execution_bridge": "temporary exact-source-derived bridge",
            "execution_budget_observer":
                "temporary bounded full-PC observer preserving exact ledger",
            "temporary_generated_objects_deleted": True,
            "timeout_milliseconds": 5000,
        },
        "portme": [
            "// PORTME at 0x84BED80C: statically prove and type the next exact boundary before authorizing any further generated instruction.",
            "// PORTME: replace 304 nonfrontier import abort definitions with exact guest-ABI semantics only as their paths become reachable.",
            "// PORTME: the function-dispatch ledger counts typed import dispatches; direct generated C++ calls remain bounded by the complete per-instruction ledger.",
            "// PORTME: recover 1,076 remaining switch-tail occurrences and complete VSCR.SAT, frsqrte/FPSCR, and cache/device coherency before broad execution.",
        ],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(result_line + "\n", encoding="utf-8")
    print(result_line)
    print(
        "APF_GUARDED_THIRD_BOUNDARY_EXECUTION_PASS "
        "instructions=283 function_dispatches=3 first=0x84BF1888 "
        "second=0x84BED7B8 third=0x84BED808 "
        "base=0x40000000 size=0x00010000 committed_pages=1 "
        "reserved_pages=15 continued_after_third=0 native_boot=0 "
        "temporary_outputs_deleted=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
