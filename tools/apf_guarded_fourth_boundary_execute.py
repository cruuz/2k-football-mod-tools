#!/usr/bin/env python3
"""Execute APF through exactly its fourth typed boundary in isolation."""

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
import apf_guarded_third_boundary_execute as third


SCHEMA = "apf2k8_guarded_fourth_boundary_execution/v1"
RESULT_PREFIX = "APF_GUARDED_FOURTH_BOUNDARY_CHILD_RESULT "
EXPECTED_XEX_SHA256 = third.EXPECTED_XEX_SHA256
EXPECTED_VOLUME_SHA256 = third.EXPECTED_VOLUME_SHA256
EXPECTED_DECODED_SHA256 = third.EXPECTED_DECODED_SHA256
EXPECTED_DECODED_SIZE = third.EXPECTED_DECODED_SIZE
EXPECTED_COMPOSED_REPORT_SHA256 = third.EXPECTED_COMPOSED_REPORT_SHA256
EXPECTED_BUDGET_REPORT_SHA256 = third.EXPECTED_BUDGET_REPORT_SHA256
EXPECTED_COMPOSED_TREE_SHA256 = third.EXPECTED_COMPOSED_TREE_SHA256
EXPECTED_INSTRUMENTED_TREE_SHA256 = third.EXPECTED_INSTRUMENTED_TREE_SHA256
EXPECTED_HOOK_MANIFEST_SHA256 = third.EXPECTED_HOOK_MANIFEST_SHA256
EXPECTED_NUMBERED_COUNT = third.EXPECTED_NUMBERED_COUNT
EXPECTED_MAPPING_COUNT = third.EXPECTED_MAPPING_COUNT
EXPECTED_HOOK_COUNT = third.EXPECTED_HOOK_COUNT
EXPECTED_IMPORT_COUNT = third.EXPECTED_IMPORT_COUNT
EXPECTED_TYPED_IMPORT_COUNT = third.EXPECTED_TYPED_IMPORT_COUNT
EXPECTED_ENTRY = third.EXPECTED_ENTRY
EXPECTED_FIRST_BRIDGE_SHA256 = third.EXPECTED_FIRST_BRIDGE_SHA256
EXPECTED_BUDGET_SOURCE_SHA256 = third.EXPECTED_BUDGET_SOURCE_SHA256
EXPECTED_LEAF_REPORT_SHA256 = third.EXPECTED_LEAF_REPORT_SHA256
EXPECTED_THIRD_DRIVER_SHA256 = (
    "7bdb109dbfc535f2c3dd869e17656e7b6541b97bce91202e6374962d099f9467"
)
EXPECTED_THIRD_REPORT_SHA256 = (
    "cf16bb85f8065812d3987216abcfae45aee775e758354e152294f5cfb4708c17"
)
EXPECTED_POST_COMMIT_STATIC_SHA256 = (
    "5831b87d8ccc75c1b418e9b3ebe2bd1da35b621214bdde094c1e65fbb9cf6148"
)
EXPECTED_POST_COMMIT_ANALYZER_SHA256 = (
    "d45b33f915652848519b85f040ba3854f29e206d2734ce887dcb0590e9c4804f"
)
EXPECTED_FOURTH_CALL = 0x84BED908
EXPECTED_FOURTH_RETURN = 0x84BED90C
EXPECTED_FOURTH_THUNK = 0x84D0868C
EXPECTED_POST_COMMIT_INSTRUCTIONS = 82
EXPECTED_CUMULATIVE_INSTRUCTIONS = 365
EXPECTED_POST_COMMIT_TRACE_SHA256 = (
    "0220f64faaaff52e8629f9a7c6d0d4d33e9d1c9c49054add334f75f926ebc967"
)
EXPECTED_INITIALIZED_PAGE_SHA256 = (
    "f0072c49de8cb307781499a69e189990e2b0837652d8afb232227f1a18da5d85"
)
EXPECTED_INITIALIZED_BACKING_FNV = 0x233B6EC7DF8372AE
INSTRUCTION_LIMIT = 4096
FUNCTION_DISPATCH_LIMIT = 64
AUTHORIZATION_TOKEN = (
    "apf2k8-v1:cf16bb85:21eaf0cd:981a5714:cde5b922:"
    "fourth-boundary-process-type-only"
)
AUTHORIZATION_NONCE = 0xA2F24008D90890C4


class FourthBoundaryError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FourthBoundaryError(message)


def sha256_file(path: Path) -> str:
    return first.sha256_file(path)


def relative(path: Path, root: Path) -> str:
    return first.relative(path, root)


def pin(path: Path, root: Path) -> dict[str, Any]:
    return first.pin(path, root)


def trace_sha256(trace: list[int]) -> str:
    return hashlib.sha256("".join(
        f"0x{pc:08X}\n" for pc in trace).encode("ascii")).hexdigest()


def evidence_header_source() -> str:
    source = third.evidence_header_source()
    for old, new in (
        ("vc_apf_third_boundary_bridge_evidence",
         "vc_apf_fourth_boundary_bridge_evidence"),
        ("vc_apf_third_boundary_mode_arm",
         "vc_apf_fourth_boundary_mode_arm"),
        ("vc_apf_third_boundary_mode_evidence",
         "vc_apf_fourth_boundary_mode_evidence"),
        ("vc_apf_third_boundary_full_trace_copy",
         "vc_apf_fourth_boundary_full_trace_copy"),
    ):
        source = source.replace(old, new)
    marker = "    std::uint32_t third_instruction_count;\n};"
    require(source.count(marker) == 1, "third evidence tail changed")
    return source.replace(marker, r'''    std::uint32_t third_instruction_count;
    std::uint32_t post_commit_vm_ledger_exact_before_continuation;
    std::uint32_t post_commit_backing_exact_before_continuation;
    std::uint32_t post_commit_global_flags_before_continuation;
    std::uint64_t post_commit_backing_fnv_before_continuation;
    std::uint32_t fourth_thunk;
    std::uint32_t fourth_lr;
    std::uint32_t fourth_r3_input;
    std::uint32_t fourth_r3_output;
    std::uint32_t fourth_instruction_count;
    std::uint32_t fourth_vm_ledger_exact_before_adapter;
    std::uint32_t fourth_initialized_backing_exact_before_adapter;
    std::uint32_t fourth_global_flags_before_adapter;
    std::uint64_t fourth_backing_fnv_before_adapter;
};''')


def specialized_budget_source(original: str) -> str:
    source = third.specialized_budget_source(original)
    source = source.replace("vc_apf_third_boundary_full_",
                            "vc_apf_fourth_boundary_full_")
    return source


def specialized_bridge_source(original: str) -> str:
    source = third.specialized_bridge_source(original)
    replacements = (
        ('#include "third_boundary_evidence.h"',
         '#include "fourth_boundary_evidence.h"'),
        ("vc_apf_third_boundary_bridge_evidence",
         "vc_apf_fourth_boundary_bridge_evidence"),
        ("vc_apf_third_boundary_mode_arm",
         "vc_apf_fourth_boundary_mode_arm"),
        ("vc_apf_third_boundary_mode_evidence",
         "vc_apf_fourth_boundary_mode_evidence"),
        ("vc_apf_third_boundary_armed", "vc_apf_fourth_boundary_armed"),
        ("vc_apf_third_boundary_observed",
         "vc_apf_fourth_boundary_observed"),
        ("UINT64_C(0xA2F23008D80880C3)",
         "UINT64_C(0xA2F24008D90890C4)"),
    )
    for old, new in replacements:
        source = source.replace(old, new)

    helper_marker = "void dispatch_and_stop(PPCContext &context, std::uint8_t *base,\n"
    require(source.count(helper_marker) == 1, "bridge dispatch marker changed")
    helpers = r'''std::uint16_t load_bridge_be_u16(const std::uint8_t *bytes) {
    return static_cast<std::uint16_t>(
        (static_cast<std::uint16_t>(bytes[0]) << 8u) |
        static_cast<std::uint16_t>(bytes[1]));
}

bool committed_vm_ledger_exact(const vc_apf_first_entry_state &state) {
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
        const std::uint8_t expected_state = index == 0u ? 2u : 1u;
        if (index < 16u) {
            if (page.allocation_id != 1u || page.state != expected_state ||
                page.protect != VC_APF_X_PAGE_READWRITE) return false;
        } else if (page.allocation_id != 0u || page.state != 0u ||
                   page.protect != 0u) return false;
    }
    return true;
}

bool post_commit_backing_exact(const vc_apf_first_entry_state &state) {
    const std::uint8_t *const bytes =
        state.adapter_runtime->config.vm_backing_bytes;
    for (std::size_t index = 0u; index < 0x00010000u; ++index) {
        if (bytes[index] != 0u) return false;
    }
    for (std::size_t index = 0x00010000u;
         index < 0x00100000u; ++index) {
        if (bytes[index] != static_cast<std::uint8_t>(
                (index * 131u + 17u) & 0xFFu)) return false;
    }
    return true;
}

bool initialized_backing_exact(const vc_apf_first_entry_state &state) {
    const std::uint8_t *const bytes =
        state.adapter_runtime->config.vm_backing_bytes;
    std::size_t nonzero = 0u;
    for (std::size_t index = 0u; index < 0x00010000u; ++index) {
        if (bytes[index] != 0u) ++nonzero;
    }
    if (nonzero != 34u || load_bridge_be_u16(bytes) != 0x0063u ||
        bytes[5] != 1u || load_bridge_be_u32(bytes + 16u) != 0xEEFFEEFFu ||
        load_bridge_be_u32(bytes + 20u) != 2u ||
        load_bridge_be_u32(bytes + 24u) != 0u ||
        load_bridge_be_u16(bytes + 58u) != 0x0610u ||
        load_bridge_be_u32(bytes + 60u) != 0u ||
        load_bridge_be_u32(bytes + 76u) != 0x40000590u ||
        load_bridge_be_u16(bytes + 368u) != 0xFFFFu) return false;
    for (std::size_t index = 0u; index < 7u; ++index) {
        const std::size_t offset = 0x590u + index * 0x10u;
        if (load_bridge_be_u32(bytes + offset) !=
            0x40000000u + offset + 0x10u)
            return false;
    }
    if (load_bridge_be_u32(bytes + 0x600u) != 0u) return false;
    for (std::size_t index = 0x00010000u;
         index < 0x00100000u; ++index) {
        if (bytes[index] != static_cast<std::uint8_t>(
                (index * 131u + 17u) & 0xFFu)) return false;
    }
    return true;
}

'''
    source = source.replace(helper_marker, helpers + helper_marker, 1)

    stage_two_marker = (
        "    if (vc_apf_fourth_boundary_observed.stage != 2u ||\n"
        "        import_thunk != VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY ||\n"
    )
    require(source.count(stage_two_marker) == 1,
            "commit-stage marker changed")
    fourth_dispatch = r'''    if (vc_apf_fourth_boundary_observed.stage == 3u) {
        const bool vm_exact = committed_vm_ledger_exact(
            *vc_apf_bound_state);
        const bool backing_exact = initialized_backing_exact(
            *vc_apf_bound_state);
        const std::uint32_t global_flags =
            load_bridge_be_u32(base + 0x852D6484u);
        const std::uint64_t backing_fnv = reserve_backing_fnv(
            *vc_apf_bound_state);
        if (import_thunk != VC_APF_THUNK_KE_GET_CURRENT_PROCESS_TYPE ||
            adapter_context.lr != 0x84BED90Cu ||
            adapter_context.gpr[3] != 0u ||
            vc_apf_bound_state->budget.function_dispatches_consumed != 3u ||
            vc_apf_guest_instruction_budget_snapshot(&trace) !=
                VC_APF_FIRST_ENTRY_OK ||
            trace.successful_instruction_count != 365u ||
            trace.recent_count == 0u ||
            trace.recent_addresses[trace.recent_count - 1u] !=
                0x84BED908u || !vm_exact || !backing_exact ||
            global_flags != 0u ||
        backing_fnv != UINT64_C(0x233B6EC7DF8372AE)) {
            stop(VC_APF_FIRST_ENTRY_NOT_AUTHORIZED,
                 VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
        }
        vc_apf_fourth_boundary_observed.fourth_thunk = import_thunk;
        vc_apf_fourth_boundary_observed.fourth_lr = adapter_context.lr;
        vc_apf_fourth_boundary_observed.fourth_r3_input =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        vc_apf_fourth_boundary_observed.fourth_instruction_count =
            static_cast<std::uint32_t>(trace.successful_instruction_count);
        vc_apf_fourth_boundary_observed
            .fourth_vm_ledger_exact_before_adapter = vm_exact ? 1u : 0u;
        vc_apf_fourth_boundary_observed
            .fourth_initialized_backing_exact_before_adapter =
            backing_exact ? 1u : 0u;
        vc_apf_fourth_boundary_observed.fourth_global_flags_before_adapter =
            global_flags;
        vc_apf_fourth_boundary_observed.fourth_backing_fnv_before_adapter =
            backing_fnv;
        gate_status = vc_apf_first_entry_dispatch_import(
            vc_apf_bound_state, &adapter_context, import_thunk,
            &adapter_status);
        for (index = 0u; index < 32u; ++index) {
            write_gpr(context, index, adapter_context.gpr[index]);
        }
        context.lr = adapter_context.lr;
        vc_apf_fourth_boundary_observed.fourth_r3_output =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        vc_apf_fourth_boundary_observed.stage = 4u;
        /* Throw unconditionally: 0x84BED90C must not execute. */
        stop(gate_status, adapter_status);
    }

'''
    source = source.replace(stage_two_marker,
                            fourth_dispatch + stage_two_marker, 1)

    old_tail = r'''    vc_apf_fourth_boundary_observed.stage = 3u;
    /* Throw unconditionally: 0x84BED80C must not execute in this milestone. */
    stop(gate_status, adapter_status);
}'''
    new_tail = r'''    const bool committed_ledger = committed_vm_ledger_exact(
        *vc_apf_bound_state);
    const bool committed_backing = post_commit_backing_exact(
        *vc_apf_bound_state);
    const std::uint32_t global_flags =
        load_bridge_be_u32(base + 0x852D6484u);
    const std::uint64_t backing_fnv = reserve_backing_fnv(
        *vc_apf_bound_state);
    vc_apf_fourth_boundary_observed
        .post_commit_vm_ledger_exact_before_continuation =
        committed_ledger ? 1u : 0u;
    vc_apf_fourth_boundary_observed
        .post_commit_backing_exact_before_continuation =
        committed_backing ? 1u : 0u;
    vc_apf_fourth_boundary_observed
        .post_commit_global_flags_before_continuation = global_flags;
    vc_apf_fourth_boundary_observed
        .post_commit_backing_fnv_before_continuation = backing_fnv;
    if (gate_status != VC_APF_FIRST_ENTRY_OK ||
        adapter_status != VC_APF_BOOT_LEAF_OK ||
        adapter_context.gpr[3] != VC_APF_X_STATUS_SUCCESS ||
        vc_apf_bound_state->budget.function_dispatches_consumed != 3u ||
        !committed_ledger || !committed_backing || global_flags != 0u ||
        backing_fnv != UINT64_C(0x8179632E8A902325)) {
        stop(gate_status, adapter_status);
    }
    vc_apf_fourth_boundary_observed.stage = 3u;
    return;
}'''
    require(source.count(old_tail) == 1, "commit terminal tail changed")
    return source.replace(old_tail, new_tail, 1)


def harness_source() -> str:
    source = third.harness_source()
    source = source.replace('#include "third_boundary_evidence.h"',
                            '#include "fourth_boundary_evidence.h"')
    source = source.replace("vc_apf_third_boundary_bridge_evidence",
                            "vc_apf_fourth_boundary_bridge_evidence")
    source = source.replace("vc_apf_third_boundary_full_trace_copy",
                            "vc_apf_fourth_boundary_full_trace_copy")
    source = source.replace("vc_apf_third_boundary_mode_evidence",
                            "vc_apf_fourth_boundary_mode_evidence")
    source = source.replace("vc_apf_third_boundary_mode_arm",
                            "vc_apf_fourth_boundary_mode_arm")
    source = source.replace(
        '"apf2k8-v1:d60c0116:1a0b9ac0:981a5714:cde5b922:'
        'third-boundary-commit-only"',
        '"apf2k8-v1:cf16bb85:21eaf0cd:981a5714:cde5b922:'
        'fourth-boundary-process-type-only"')
    source = source.replace("UINT64_C(0xA2F23008D80880C3)",
                            "UINT64_C(0xA2F24008D90890C4)")
    source = source.replace("constexpr std::uint32_t kMagic = 0x41504634u;",
                            "constexpr std::uint32_t kMagic = 0x41504635u;")
    constants_marker = "constexpr std::uint32_t kCommitSize = 0x00010000u;\n"
    require(source.count(constants_marker) == 1, "harness constants changed")
    source = source.replace(constants_marker, constants_marker + r'''constexpr std::uint32_t kExpectedFourthThunk = 0x84D0868Cu;
constexpr std::uint32_t kExpectedFourthCall = 0x84BED908u;
constexpr std::uint32_t kExpectedFourthReturn = 0x84BED90Cu;
''', 1)
    source = source.replace("expected_third_boundary",
                            "expected_fourth_boundary")
    source = source.replace("first_page_zeroed", "initialized_page_exact")

    fn_marker = "std::int64_t monotonic_milliseconds() {\n"
    require(source.count(fn_marker) == 1, "harness helper marker changed")
    page_helper = r'''bool initialized_page_exact(const std::uint8_t *bytes) {
    std::size_t nonzero = 0u;
    for (std::size_t index = 0u; index < 0x10000u; ++index) {
        if (bytes[index] != 0u) ++nonzero;
    }
    if (nonzero != 34u || load_be_u32(bytes + 16u) != 0xEEFFEEFFu ||
        load_be_u32(bytes + 20u) != 2u ||
        load_be_u32(bytes + 24u) != 0u ||
        load_be_u32(bytes + 60u) != 0u ||
        load_be_u32(bytes + 76u) != 0x40000590u ||
        load_be_u32(bytes + 0x600u) != 0u || bytes[0] != 0u ||
        bytes[1] != 0x63u || bytes[5] != 1u || bytes[58] != 0x06u ||
        bytes[59] != 0x10u || bytes[368] != 0xFFu ||
        bytes[369] != 0xFFu) return false;
    for (std::size_t index = 0u; index < 7u; ++index) {
        const std::size_t offset = 0x590u + index * 0x10u;
        if (load_be_u32(bytes + offset) !=
            0x40000000u + offset + 0x10u) return false;
    }
    return true;
}

'''
    source = source.replace(fn_marker, page_helper + fn_marker, 1)

    catch_old = (
        "report.outcome = stop.import_thunk == kExpectedThirdThunk\n"
        "                             ? child_outcome::expected_fourth_boundary\n"
    )
    catch_new = (
        "report.outcome = stop.import_thunk == kExpectedFourthThunk\n"
        "                             ? child_outcome::expected_fourth_boundary\n"
    )
    require(source.count(catch_old) == 1, "harness catch gate changed")
    source = source.replace(catch_old, catch_new, 1)

    old_page = r'''    report.initialized_page_exact = 1u;
    for (std::uint32_t index = 0u; index < kCommitSize; ++index) {
        if (vm_backing[index] != 0u) {
            report.initialized_page_exact = 0u;
            break;
        }
    }'''
    new_page = r'''    report.initialized_page_exact =
        initialized_page_exact(vm_backing) ? 1u : 0u;'''
    require(source.count(old_page) == 1, "harness page check changed")
    source = source.replace(old_page, new_page, 1)

    expected_start = source.index("    const bool expected =\n")
    expected_end = source.index(
        "\n    vc_apf_guest_instruction_budget_unbind();", expected_start)
    expected = r'''    const bool expected =
        report.outcome == child_outcome::expected_fourth_boundary &&
        report.gate_status == VC_APF_FIRST_ENTRY_OK &&
        report.adapter_status == VC_APF_BOOT_LEAF_OK &&
        report.import_thunk == kExpectedFourthThunk &&
        report.instructions_consumed == 365u &&
        report.function_dispatches_consumed == 4u &&
        report.trace_count == 365u &&
        report.last_guest_address == kExpectedFourthCall &&
        report.context_lr == kExpectedFourthReturn &&
        report.context_r3 == 1u && report.bridge.stage == 4u &&
        report.bridge.first_instruction_count == 38u &&
        report.bridge.second_instruction_count == 264u &&
        report.bridge.third_instruction_count == 283u &&
        report.bridge.third_thunk == kExpectedThirdThunk &&
        report.bridge.third_lr == kExpectedThirdReturn &&
        report.bridge.third_r3_output == VC_APF_X_STATUS_SUCCESS &&
        report.bridge.post_commit_vm_ledger_exact_before_continuation == 1u &&
        report.bridge.post_commit_backing_exact_before_continuation == 1u &&
        report.bridge.post_commit_global_flags_before_continuation == 0u &&
        report.bridge.post_commit_backing_fnv_before_continuation ==
            UINT64_C(0x8179632E8A902325) &&
        report.bridge.fourth_thunk == kExpectedFourthThunk &&
        report.bridge.fourth_lr == kExpectedFourthReturn &&
        report.bridge.fourth_r3_input == 0u &&
        report.bridge.fourth_r3_output == 1u &&
        report.bridge.fourth_instruction_count == 365u &&
        report.bridge.fourth_vm_ledger_exact_before_adapter == 1u &&
        report.bridge.fourth_initialized_backing_exact_before_adapter == 1u &&
        report.bridge.fourth_global_flags_before_adapter == 0u &&
        report.bridge.fourth_backing_fnv_before_adapter ==
            UINT64_C(0x233B6EC7DF8372AE) &&
        report.vm_page_count == 4096u &&
        report.vm_allocation_count == 1u &&
        report.reserved_page_count == 15u &&
        report.committed_page_count == 1u &&
        report.vm_ledger_exact == 1u &&
        report.initialized_page_exact == 1u &&
        report.remaining_backing_pattern_exact == 1u &&
        report.backing_fnv_before == UINT64_C(0x1F5E0DF9BC822325) &&
        report.backing_fnv_after == UINT64_C(0x233B6EC7DF8372AE);
    if (report.outcome == child_outcome::expected_fourth_boundary &&
        !expected) {
        report.outcome = child_outcome::unexpected_exception;
    }
'''
    source = source[:expected_start] + expected + source[expected_end:]

    output_start = source.index("    if (timed_out) {\n", source.index("int main("))
    output_end = source.index("\n}\n", output_start) + 2
    output = r'''    if (timed_out) {
        std::printf("APF_GUARDED_FOURTH_BOUNDARY_CHILD_RESULT outcome=timeout "
                    "signal=%d containment_normal=1 containment_signal=1 "
                    "containment_timeout=1\n", SIGKILL);
        return 20;
    }
    if (WIFSIGNALED(wait_status)) {
        std::printf("APF_GUARDED_FOURTH_BOUNDARY_CHILD_RESULT outcome=signal "
                    "signal=%d containment_normal=1 containment_signal=1 "
                    "containment_timeout=1\n", WTERMSIG(wait_status));
        return 21;
    }
    if (!WIFEXITED(wait_status) || WEXITSTATUS(wait_status) != 0 ||
        received != sizeof(report) || report.magic != kMagic) {
        std::printf("APF_GUARDED_FOURTH_BOUNDARY_CHILD_RESULT "
                    "outcome=import_abort signal=0 report_missing=1 "
                    "containment_normal=1 containment_signal=1 "
                    "containment_timeout=1\n");
        return 22;
    }
    std::printf(
        "APF_GUARDED_FOURTH_BOUNDARY_CHILD_RESULT outcome=%s signal=0 "
        "entry_authorized=%u entry_called=%u prerequisite_step=%u "
        "gate_status=%u adapter_status=%u thunk=0x%08X stage=%u "
        "instructions=%llu function_dispatches=%llu last_pc=0x%08X "
        "lr=0x%08X r3=0x%08X first_instructions=%u "
        "second_instructions=%u third_instructions=%u "
        "post_commit_ledger=%u post_commit_backing=%u "
        "post_commit_global=0x%08X post_commit_fnv=0x%016llX "
        "fourth_instructions=%u fourth_thunk=0x%08X fourth_lr=0x%08X "
        "fourth_r3_in=0x%08X fourth_r3_out=0x%08X fourth_ledger=%u "
        "fourth_backing=%u fourth_global=0x%08X fourth_fnv=0x%016llX "
        "vm_pages=%u vm_allocations=%u reserved_pages=%u "
        "committed_pages=%u ledger_exact=%u initialized_page_exact=%u "
        "remaining_pattern_exact=%u backing_fnv_before=0x%016llX "
        "backing_fnv_after=0x%016llX trace=",
        outcome_name(report.outcome), report.entry_authorized,
        report.entry_called, report.prerequisite_step, report.gate_status,
        report.adapter_status, report.import_thunk, report.bridge.stage,
        static_cast<unsigned long long>(report.instructions_consumed),
        static_cast<unsigned long long>(
            report.function_dispatches_consumed),
        report.last_guest_address, report.context_lr, report.context_r3,
        report.bridge.first_instruction_count,
        report.bridge.second_instruction_count,
        report.bridge.third_instruction_count,
        report.bridge.post_commit_vm_ledger_exact_before_continuation,
        report.bridge.post_commit_backing_exact_before_continuation,
        report.bridge.post_commit_global_flags_before_continuation,
        static_cast<unsigned long long>(
            report.bridge.post_commit_backing_fnv_before_continuation),
        report.bridge.fourth_instruction_count,
        report.bridge.fourth_thunk, report.bridge.fourth_lr,
        report.bridge.fourth_r3_input, report.bridge.fourth_r3_output,
        report.bridge.fourth_vm_ledger_exact_before_adapter,
        report.bridge.fourth_initialized_backing_exact_before_adapter,
        report.bridge.fourth_global_flags_before_adapter,
        static_cast<unsigned long long>(
            report.bridge.fourth_backing_fnv_before_adapter),
        report.vm_page_count, report.vm_allocation_count,
        report.reserved_page_count, report.committed_page_count,
        report.vm_ledger_exact, report.initialized_page_exact,
        report.remaining_backing_pattern_exact,
        static_cast<unsigned long long>(report.backing_fnv_before),
        static_cast<unsigned long long>(report.backing_fnv_after));
    for (std::uint32_t index = 0u; index < report.trace_count; ++index) {
        std::printf("%s%08X", index == 0u ? "" : ",",
                    report.trace[index]);
    }
    std::printf(" containment_normal=1 containment_signal=1 "
                "containment_timeout=1\n");
    return report.outcome == child_outcome::expected_fourth_boundary ? 0 : 23;
}'''
    source = source[:output_start] + output + source[output_end:]
    source = source.replace("APF_GUARDED_THIRD_BOUNDARY_CHILD_RESULT",
                            "APF_GUARDED_FOURTH_BOUNDARY_CHILD_RESULT")
    return source


def parse_result_line(line: str) -> dict[str, str]:
    require(line.startswith(RESULT_PREFIX), "fourth result prefix changed")
    fields: dict[str, str] = {}
    for token in line[len(RESULT_PREFIX):].split():
        require("=" in token, f"malformed result token: {token}")
        key, value = token.split("=", 1)
        require(key not in fields, f"duplicate result field: {key}")
        fields[key] = value
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
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
    decoded = resolve(args.decoded)
    output_json = resolve(args.json)
    transcript = resolve(args.transcript)
    temp_root = resolve(args.temp_root)
    xex = root / "extracted/All-Pro Football 2K8 (USA)/default.xex"
    volume = root / "extracted/All-Pro Football 2K8 (USA)/0A"
    third_report_path = root / (
        "reports/static_recomp/apf2k8_guarded_third_boundary_execution.json")
    post_commit_path = root / (
        "reports/static_recomp/apf2k8_post_commit_static.json")
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
    third_driver_path = root / "tools/apf_guarded_third_boundary_execute.py"
    post_commit_analyzer_path = root / "tools/apf_post_commit_static.py"
    clang = shutil.which(args.clang)
    clangxx = shutil.which(args.clangxx)
    required = [
        decoded, xex, volume, third_report_path, post_commit_path,
        composed_report_path, budget_report_path, leaf_report_path,
        xex_report_path, first_bridge_path, budget_source_path,
        third_driver_path, post_commit_analyzer_path,
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "src/static_runtime/apf_boot_leaf_adapters.c",
    ]
    require(args.jobs > 0 and clang is not None and clangxx is not None and
            all(path.is_file() and not path.is_symlink() for path in required),
            "fourth-boundary prerequisite missing")
    require(sha256_file(xex) == EXPECTED_XEX_SHA256 and
            sha256_file(volume) == EXPECTED_VOLUME_SHA256,
            "retail APF input hash changed")
    require(decoded.stat().st_size == EXPECTED_DECODED_SIZE and
            sha256_file(decoded) == EXPECTED_DECODED_SHA256,
            "decoded APF image changed")
    require(sha256_file(third_report_path) == EXPECTED_THIRD_REPORT_SHA256 and
            sha256_file(post_commit_path) ==
                EXPECTED_POST_COMMIT_STATIC_SHA256 and
            sha256_file(third_driver_path) == EXPECTED_THIRD_DRIVER_SHA256 and
            sha256_file(post_commit_analyzer_path) ==
                EXPECTED_POST_COMMIT_ANALYZER_SHA256 and
            sha256_file(first_bridge_path) == EXPECTED_FIRST_BRIDGE_SHA256 and
            sha256_file(budget_source_path) == EXPECTED_BUDGET_SOURCE_SHA256 and
            sha256_file(leaf_report_path) == EXPECTED_LEAF_REPORT_SHA256 and
            sha256_file(composed_report_path) ==
                EXPECTED_COMPOSED_REPORT_SHA256 and
            sha256_file(budget_report_path) == EXPECTED_BUDGET_REPORT_SHA256,
            "pinned APF evidence changed")

    prior = json.loads(third_report_path.read_text(encoding="utf-8"))
    static = json.loads(post_commit_path.read_text(encoding="utf-8"))
    require(prior["result"]["child_outcome"] ==
            "expected_third_boundary" and
            prior["generated_execution"][
                "executed_guest_instruction_count"] == 283 and
            prior["virtual_memory_ledger"]["committed_page_count"] == 1,
            "guarded third checkpoint semantics changed")
    require(static["schema"] == "apf2k8_post_commit_static/v1" and
            static["static_trace"][
                "continuation_instruction_count_through_next_call"] == 82 and
            static["static_trace"][
                "cumulative_instruction_count_through_next_call"] == 365 and
            static["static_trace"]["ordered_pc_sha256"] ==
                EXPECTED_POST_COMMIT_TRACE_SHA256 and
            static["next_boundary"]["call_pc"] == "0x84BED908" and
            static["next_boundary"]["return_pc"] == "0x84BED90C" and
            static["next_boundary"]["thunk"] == "0x84D0868C",
            "post-commit static proof changed")

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
            typed_imports < all_imports,
            "typed import split changed")
    nonfrontier = sorted(all_imports - typed_imports)

    bridge = specialized_bridge_source(original_bridge)
    budget = specialized_budget_source(
        budget_source_path.read_text(encoding="utf-8"))
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apf-fourth-boundary-v1-",
                                     dir=temp_root) as temporary:
        build = Path(temporary)
        files = {
            "abort": build / "nonfrontier_abort.h",
            "stubs": build / "nonfrontier_imports.cpp",
            "evidence": build / "fourth_boundary_evidence.h",
            "bridge": build / "fourth_boundary_bridge.cpp",
            "budget": build / "fourth_boundary_budget.cpp",
            "harness": build / "guarded_fourth_driver.cpp",
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
        require(not failures, "fourth-boundary compilation failed: " +
                " | ".join(item["stderr"][-2000:] for item in failures[:3]))
        executable = build / "apf_guarded_fourth_boundary_v1"
        linked = subprocess.run([
            clangxx, "-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie",
            *[str(target) for _, target in specs], "-lm", "-o", str(executable),
        ], capture_output=True, text=True, check=False)
        require(linked.returncode == 0,
                "fourth-boundary link failed: " + linked.stderr[-2400:])
        executed = subprocess.run([
            str(executable), str(decoded), str(xex), AUTHORIZATION_TOKEN,
        ], capture_output=True, text=True, check=False, timeout=30)
        require(executed.returncode == 0,
                f"fourth child changed ({executed.returncode}): " +
                executed.stdout[-5000:] + executed.stderr[-2400:])
        lines = [line for line in executed.stdout.splitlines()
                 if line.startswith(RESULT_PREFIX)]
        require(len(lines) == 1 and executed.stderr == "",
                "fourth child transcript changed")
        result_line = lines[0]
        fields = parse_result_line(result_line)

    exact = {
        "outcome": "expected_fourth_boundary", "signal": "0",
        "entry_authorized": "1", "entry_called": "1",
        "prerequisite_step": "6", "gate_status": "0",
        "adapter_status": "0", "stage": "4", "instructions": "365",
        "function_dispatches": "4", "first_instructions": "38",
        "second_instructions": "264", "third_instructions": "283",
        "post_commit_ledger": "1", "post_commit_backing": "1",
        "fourth_instructions": "365", "fourth_ledger": "1",
        "fourth_backing": "1", "reserved_pages": "15",
        "committed_pages": "1", "ledger_exact": "1",
        "initialized_page_exact": "1", "remaining_pattern_exact": "1",
        "containment_normal": "1", "containment_signal": "1",
        "containment_timeout": "1",
    }
    require(all(fields.get(key) == value for key, value in exact.items()),
            "fourth result scalar changed")
    expected_hex = {
        "thunk": EXPECTED_FOURTH_THUNK,
        "last_pc": EXPECTED_FOURTH_CALL,
        "lr": EXPECTED_FOURTH_RETURN,
        "r3": 1,
        "post_commit_global": 0,
        "post_commit_fnv": 0x8179632E8A902325,
        "fourth_thunk": EXPECTED_FOURTH_THUNK,
        "fourth_lr": EXPECTED_FOURTH_RETURN,
        "fourth_r3_in": 0,
        "fourth_r3_out": 1,
        "fourth_global": 0,
        "fourth_fnv": EXPECTED_INITIALIZED_BACKING_FNV,
        "backing_fnv_before": 0x1F5E0DF9BC822325,
        "backing_fnv_after": EXPECTED_INITIALIZED_BACKING_FNV,
    }
    require(all(int(fields.get(key, "-1"), 0) == value
                for key, value in expected_hex.items()),
            "fourth ABI/state changed")
    trace = [int(value, 16) for value in fields["trace"].split(",") if value]
    require(len(trace) == EXPECTED_CUMULATIVE_INSTRUCTIONS and
            trace[282] == 0x84BED808 and trace[283] == 0x84BED80C and
            trace[-1] == EXPECTED_FOURTH_CALL,
            "fourth dynamic trace endpoints changed")
    continuation = trace[283:]
    continuation_sha = trace_sha256(continuation)
    require(len(continuation) == EXPECTED_POST_COMMIT_INSTRUCTIONS and
            continuation_sha == EXPECTED_POST_COMMIT_TRACE_SHA256 ==
                static["static_trace"]["ordered_pc_sha256"],
            "fourth dynamic/static trace mismatch")

    local_files = [
        first_bridge_path, budget_source_path,
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "src/static_runtime/apf_boot_leaf_adapters.c",
        third_driver_path, post_commit_analyzer_path,
        root / "tools/apf_guarded_fourth_boundary_execute.py",
    ]
    report = {
        "schema": SCHEMA,
        "result": {
            "guarded_third_boundary_execution_revalidated": True,
            "post_commit_static_proof_revalidated": True,
            "translated_title_code_executed": True,
            "continued_past_third_typed_boundary": True,
            "expected_fourth_typed_boundary_reached": True,
            "fourth_typed_adapter_completed": True,
            "continued_past_fourth_typed_boundary": False,
            "child_outcome": fields["outcome"],
            "signal_number": 0,
            "native_boot_proved": False,
            "main_menu_proved": False,
        },
        "authorization_gates": {
            "retail_xex_sha256_exact": True,
            "retail_volume_sha256_exact": True,
            "decoded_image_sha256_and_size_exact": True,
            "guarded_third_report_exact": True,
            "post_commit_static_report_exact": True,
            "composed_and_instrumented_complete_trees_exact": True,
            "instruction_hook_count": hook_count,
            "mapping_count": mapping_count,
            "typed_import_count": len(typed_imports),
            "post_commit_vm_ledger_exact_before_continuation": True,
            "post_commit_backing_exact_before_continuation": True,
            "post_commit_global_flags_exact_before_continuation": True,
            "fourth_dynamic_pc_lr_state_gate": True,
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
            "post_commit_ordered_pc_sha256": continuation_sha,
            "ordered_guest_pcs": [f"0x{pc:08X}" for pc in trace],
            "fourth_boundary": {
                "import": "KeGetCurrentProcessType",
                "call_pc": f"0x{EXPECTED_FOURTH_CALL:08X}",
                "return_pc": f"0x{EXPECTED_FOURTH_RETURN:08X}",
                "thunk": f"0x{EXPECTED_FOURTH_THUNK:08X}",
                "instruction_count_at_call": len(trace),
                "arguments": {},
                "r3_before_adapter": fields["fourth_r3_in"],
                "r3_process_type_result": fields["fourth_r3_out"],
                "adapter_status": "ok",
                "generated_return_instruction_executed": False,
                "terminal_semantics": (
                    "existing typed process-type adapter completed; bridge "
                    "threw before generated instruction 0x84BED90C"
                ),
            },
        },
        "virtual_memory_and_initialization": {
            "active_allocation_count": 1,
            "allocation_page_count": 16,
            "committed_page_count": 1,
            "remaining_reserved_page_count": 15,
            "vm_ledger_exact": True,
            "initialized_committed_page_exact": True,
            "initialized_committed_page_sha256":
                EXPECTED_INITIALIZED_PAGE_SHA256,
            "initialized_nonzero_byte_count": 34,
            "remaining_15_page_pattern_exact": True,
            "allocation_fnv1a64_after_initialization":
                fields["backing_fnv_after"],
            "global_flags_be_u32": fields["fourth_global"],
        },
        "inputs": {
            "retail_xex": pin(xex, root),
            "retail_volume": pin(volume, root),
            "decoded_image": {
                "size": decoded.stat().st_size,
                "sha256": sha256_file(decoded),
                "temporary_validator_artifact": True,
            },
            "guarded_third_report": pin(third_report_path, root),
            "post_commit_static_report": pin(post_commit_path, root),
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
            "// PORTME at 0x84BED90C: statically prove and type the next exact boundary before authorizing any further generated instruction.",
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
        "APF_GUARDED_FOURTH_BOUNDARY_EXECUTION_PASS instructions=365 "
        "function_dispatches=4 fourth=0x84BED908 process_type=1 "
        "committed_pages=1 reserved_pages=15 continued_after_fourth=0 "
        "native_boot=0 temporary_outputs_deleted=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
