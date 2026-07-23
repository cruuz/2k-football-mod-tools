#!/usr/bin/env python3
"""Execute APF through exactly its fifth typed boundary in isolation."""

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
import apf_guarded_fourth_boundary_execute as fourth


SCHEMA = "apf2k8_guarded_fifth_boundary_execution/v1"
RESULT_PREFIX = "APF_GUARDED_FIFTH_BOUNDARY_CHILD_RESULT "
EXPECTED_XEX_SHA256 = fourth.EXPECTED_XEX_SHA256
EXPECTED_VOLUME_SHA256 = fourth.EXPECTED_VOLUME_SHA256
EXPECTED_DECODED_SHA256 = fourth.EXPECTED_DECODED_SHA256
EXPECTED_DECODED_SIZE = fourth.EXPECTED_DECODED_SIZE
EXPECTED_COMPOSED_REPORT_SHA256 = fourth.EXPECTED_COMPOSED_REPORT_SHA256
EXPECTED_BUDGET_REPORT_SHA256 = fourth.EXPECTED_BUDGET_REPORT_SHA256
EXPECTED_COMPOSED_TREE_SHA256 = fourth.EXPECTED_COMPOSED_TREE_SHA256
EXPECTED_INSTRUMENTED_TREE_SHA256 = fourth.EXPECTED_INSTRUMENTED_TREE_SHA256
EXPECTED_HOOK_MANIFEST_SHA256 = fourth.EXPECTED_HOOK_MANIFEST_SHA256
EXPECTED_NUMBERED_COUNT = fourth.EXPECTED_NUMBERED_COUNT
EXPECTED_MAPPING_COUNT = fourth.EXPECTED_MAPPING_COUNT
EXPECTED_HOOK_COUNT = fourth.EXPECTED_HOOK_COUNT
EXPECTED_IMPORT_COUNT = fourth.EXPECTED_IMPORT_COUNT
EXPECTED_TYPED_IMPORT_COUNT = fourth.EXPECTED_TYPED_IMPORT_COUNT
EXPECTED_ENTRY = fourth.EXPECTED_ENTRY
EXPECTED_FIRST_BRIDGE_SHA256 = fourth.EXPECTED_FIRST_BRIDGE_SHA256
EXPECTED_BUDGET_SOURCE_SHA256 = fourth.EXPECTED_BUDGET_SOURCE_SHA256
EXPECTED_LEAF_REPORT_SHA256 = fourth.EXPECTED_LEAF_REPORT_SHA256
EXPECTED_FOURTH_DRIVER_SHA256 = (
    "7a4af9c78ce600695f9f83b9904083e9cdeab024692aab30d244c9ff4c85c4c3"
)
EXPECTED_FOURTH_REPORT_SHA256 = (
    "98403d883c3e20c69e2655482f67353ff30f68e24bd1815e7366de731c529b08"
)
EXPECTED_POST_PROCESS_STATIC_SHA256 = (
    "1ad608809fd15e44c50c3ef7601683a0d90a6a658f4e86636ec3d3c0b39f08c3"
)
EXPECTED_POST_PROCESS_ANALYZER_SHA256 = (
    "de6c8337cd13afcb6db92b777d5d89f60b0a1da0f16b27fe69182c63d4e4e41c"
)
EXPECTED_FIFTH_CALL = 0x84BED954
EXPECTED_FIFTH_RETURN = 0x84BED958
EXPECTED_FIFTH_THUNK = 0x84D07FBC
EXPECTED_FIFTH_ARGUMENT = 0x40000610
EXPECTED_CONTINUATION_INSTRUCTIONS = 654
EXPECTED_CUMULATIVE_INSTRUCTIONS = 1019
EXPECTED_CONTINUATION_TRACE_SHA256 = (
    "8bb54714bb3065e9ca2af5c03795b0978e8a5d86246549f88f49d8a25900529d"
)
EXPECTED_PRE_FIFTH_PAGE_SHA256 = (
    "8174339c35c7a8d0f68fcce0ed9c10697dad9fe6a7a0237e0d6738a35edfda07"
)
EXPECTED_PRE_FIFTH_BACKING_FNV = 0xF663B4BBF571B2AD
EXPECTED_POST_FIFTH_PAGE_SHA256 = (
    "87438b39f9268a5dd7e49711573bd66cab9b0bb378579b0ddd962b884506f1f3"
)
EXPECTED_POST_FIFTH_BACKING_FNV = 0xD0D16B728ECA1764
INSTRUCTION_LIMIT = 4096
FUNCTION_DISPATCH_LIMIT = 64
AUTHORIZATION_TOKEN = (
    "apf2k8-v1:98403d88:1ad60880:981a5714:cde5b922:"
    "fifth-boundary-critical-section-only"
)
AUTHORIZATION_NONCE = 0xA2F25009D9549585


class FifthBoundaryError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FifthBoundaryError(message)


def sha256_file(path: Path) -> str:
    return first.sha256_file(path)


def pin(path: Path, root: Path) -> dict[str, Any]:
    return first.pin(path, root)


def trace_sha256(trace: list[int]) -> str:
    return hashlib.sha256("".join(
        f"0x{pc:08X}\n" for pc in trace).encode("ascii")).hexdigest()


def evidence_header_source() -> str:
    source = fourth.evidence_header_source()
    source = source.replace("vc_apf_fourth_boundary_",
                            "vc_apf_fifth_boundary_")
    marker = "    std::uint64_t fourth_backing_fnv_before_adapter;\n};"
    require(source.count(marker) == 1, "fourth evidence tail changed")
    return source.replace(marker, r'''    std::uint64_t fourth_backing_fnv_before_adapter;
    std::uint32_t fifth_thunk;
    std::uint32_t fifth_lr;
    std::uint32_t fifth_r3_input;
    std::uint32_t fifth_r3_output;
    std::uint32_t fifth_r21_input;
    std::uint32_t fifth_r29_input;
    std::uint32_t fifth_instruction_count;
    std::uint32_t fifth_vm_ledger_exact_before_adapter;
    std::uint32_t fifth_page_exact_before_adapter;
    std::uint32_t fifth_global_flags_before_adapter;
    std::uint64_t fifth_backing_fnv_before_adapter;
    std::uint32_t fifth_critical_section_exact_after_adapter;
    std::uint64_t fifth_backing_fnv_after_adapter;
};''')


def specialized_budget_source(original: str) -> str:
    source = fourth.specialized_budget_source(original)
    return source.replace("vc_apf_fourth_boundary_full_",
                          "vc_apf_fifth_boundary_full_")


def specialized_bridge_source(original: str) -> str:
    source = fourth.specialized_bridge_source(original)
    replacements = (
        ('#include "fourth_boundary_evidence.h"',
         '#include "fifth_boundary_evidence.h"'),
        ("vc_apf_fourth_boundary_", "vc_apf_fifth_boundary_"),
        ("UINT64_C(0xA2F24008D90890C4)",
         "UINT64_C(0xA2F25009D9549585)"),
    )
    for old, new in replacements:
        source = source.replace(old, new)

    dispatch_marker = "void dispatch_and_stop(PPCContext &context, std::uint8_t *base,\n"
    require(source.count(dispatch_marker) == 1,
            "fifth bridge dispatch marker changed")
    helpers = r'''bool post_process_type_backing_exact(
    const vc_apf_first_entry_state &state, bool critical_initialized) {
    const std::uint8_t *const bytes =
        state.adapter_runtime->config.vm_backing_bytes;
    const std::size_t expected_nonzero = critical_initialized ? 811u : 799u;
    std::size_t nonzero = 0u;
    for (std::size_t index = 0u; index < 0x00010000u; ++index) {
        if (bytes[index] != 0u) ++nonzero;
    }
    if (nonzero != expected_nonzero || load_bridge_be_u16(bytes) != 0x0063u ||
        bytes[5] != 1u || load_bridge_be_u32(bytes + 16u) != 0xEEFFEEFFu ||
        load_bridge_be_u32(bytes + 20u) != 2u ||
        load_bridge_be_u32(bytes + 24u) != 0u ||
        load_bridge_be_u16(bytes + 58u) != 0x0610u ||
        load_bridge_be_u32(bytes + 60u) != 0u ||
        load_bridge_be_u32(bytes + 76u) != 0x40000590u ||
        load_bridge_be_u32(bytes + 88u) != 0x40000058u ||
        load_bridge_be_u32(bytes + 92u) != 0x40000058u ||
        load_bridge_be_u16(bytes + 368u) != 0xFFFFu || bytes[379] != 1u)
        return false;
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
    if (load_bridge_be_u32(bytes + 0x600u) != 0u) return false;
    if (critical_initialized) {
        if (load_bridge_be_u32(bytes + 0x610u) != 0x01000400u ||
            load_bridge_be_u32(bytes + 0x614u) != 0u ||
            load_bridge_be_u32(bytes + 0x618u) != 0x40000618u ||
            load_bridge_be_u32(bytes + 0x61Cu) != 0x40000618u ||
            load_bridge_be_u32(bytes + 0x620u) != 0xFFFFFFFFu ||
            load_bridge_be_u32(bytes + 0x624u) != 0u ||
            load_bridge_be_u32(bytes + 0x628u) != 0u) return false;
    } else {
        for (std::size_t index = 0x610u; index < 0x62Cu; ++index) {
            if (bytes[index] != 0u) return false;
        }
    }
    for (std::size_t index = 0x00010000u;
         index < 0x00100000u; ++index) {
        if (bytes[index] != static_cast<std::uint8_t>(
                (index * 131u + 17u) & 0xFFu)) return false;
    }
    return true;
}

'''
    source = source.replace(dispatch_marker, helpers + dispatch_marker, 1)

    old_fourth_tail = r'''        vc_apf_fifth_boundary_observed.fourth_r3_output =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        vc_apf_fifth_boundary_observed.stage = 4u;
        /* Throw unconditionally: 0x84BED90C must not execute. */
        stop(gate_status, adapter_status);
    }
'''
    new_fourth_tail = r'''        vc_apf_fifth_boundary_observed.fourth_r3_output =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        if (gate_status != VC_APF_FIRST_ENTRY_OK ||
            adapter_status != VC_APF_BOOT_LEAF_OK ||
            adapter_context.gpr[3] != 1u ||
            vc_apf_bound_state->budget.function_dispatches_consumed != 4u) {
            stop(gate_status, adapter_status);
        }
        vc_apf_fifth_boundary_observed.stage = 4u;
        return;
    }
'''
    require(source.count(old_fourth_tail) == 1,
            "fourth terminal dispatch changed")
    source = source.replace(old_fourth_tail, new_fourth_tail, 1)

    stage_two_marker = (
        "    if (vc_apf_fifth_boundary_observed.stage != 2u ||\n"
        "        import_thunk != VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY ||\n"
    )
    require(source.count(stage_two_marker) == 1,
            "commit-stage marker changed")
    fifth_dispatch = r'''    if (vc_apf_fifth_boundary_observed.stage == 4u) {
        const bool vm_exact = committed_vm_ledger_exact(*vc_apf_bound_state);
        const bool page_exact = post_process_type_backing_exact(
            *vc_apf_bound_state, false);
        const std::uint32_t global_flags =
            load_bridge_be_u32(base + 0x852D6484u);
        const std::uint64_t backing_fnv = reserve_backing_fnv(
            *vc_apf_bound_state);
        if (import_thunk != VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION ||
            adapter_context.lr != 0x84BED958u ||
            adapter_context.gpr[3] != UINT64_C(0x40000610) ||
            adapter_context.gpr[21] != UINT64_C(0x40000610) ||
            adapter_context.gpr[29] != UINT64_C(0x40000610) ||
            vc_apf_bound_state->budget.function_dispatches_consumed != 4u ||
            vc_apf_guest_instruction_budget_snapshot(&trace) !=
                VC_APF_FIRST_ENTRY_OK ||
            trace.successful_instruction_count != 1019u ||
            trace.recent_count == 0u ||
            trace.recent_addresses[trace.recent_count - 1u] !=
                0x84BED954u || !vm_exact || !page_exact ||
            global_flags != 0u ||
            backing_fnv != UINT64_C(0xF663B4BBF571B2AD)) {
            stop(VC_APF_FIRST_ENTRY_NOT_AUTHORIZED,
                 VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
        }
        vc_apf_fifth_boundary_observed.fifth_thunk = import_thunk;
        vc_apf_fifth_boundary_observed.fifth_lr = adapter_context.lr;
        vc_apf_fifth_boundary_observed.fifth_r3_input =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        vc_apf_fifth_boundary_observed.fifth_r21_input =
            static_cast<std::uint32_t>(adapter_context.gpr[21]);
        vc_apf_fifth_boundary_observed.fifth_r29_input =
            static_cast<std::uint32_t>(adapter_context.gpr[29]);
        vc_apf_fifth_boundary_observed.fifth_instruction_count =
            static_cast<std::uint32_t>(trace.successful_instruction_count);
        vc_apf_fifth_boundary_observed
            .fifth_vm_ledger_exact_before_adapter = vm_exact ? 1u : 0u;
        vc_apf_fifth_boundary_observed.fifth_page_exact_before_adapter =
            page_exact ? 1u : 0u;
        vc_apf_fifth_boundary_observed.fifth_global_flags_before_adapter =
            global_flags;
        vc_apf_fifth_boundary_observed.fifth_backing_fnv_before_adapter =
            backing_fnv;
        gate_status = vc_apf_first_entry_dispatch_import(
            vc_apf_bound_state, &adapter_context, import_thunk,
            &adapter_status);
        for (index = 0u; index < 32u; ++index) {
            write_gpr(context, index, adapter_context.gpr[index]);
        }
        context.lr = adapter_context.lr;
        vc_apf_fifth_boundary_observed.fifth_r3_output =
            static_cast<std::uint32_t>(adapter_context.gpr[3]);
        vc_apf_fifth_boundary_observed
            .fifth_critical_section_exact_after_adapter =
            post_process_type_backing_exact(
                *vc_apf_bound_state, true) ? 1u : 0u;
        vc_apf_fifth_boundary_observed.fifth_backing_fnv_after_adapter =
            reserve_backing_fnv(*vc_apf_bound_state);
        vc_apf_fifth_boundary_observed.stage = 5u;
        /* Throw unconditionally: 0x84BED958 must not execute. */
        stop(gate_status, adapter_status);
    }

'''
    return source.replace(stage_two_marker,
                          fifth_dispatch + stage_two_marker, 1)


def harness_source() -> str:
    source = fourth.harness_source()
    source = source.replace('#include "fourth_boundary_evidence.h"',
                            '#include "fifth_boundary_evidence.h"')
    source = source.replace("vc_apf_fourth_boundary_",
                            "vc_apf_fifth_boundary_")
    source = source.replace("APF_GUARDED_FOURTH_BOUNDARY_CHILD_RESULT",
                            "APF_GUARDED_FIFTH_BOUNDARY_CHILD_RESULT")
    source = source.replace("expected_fourth_boundary",
                            "expected_fifth_boundary")
    source = source.replace(
        "apf2k8-v1:cf16bb85:21eaf0cd:981a5714:cde5b922:"
        "fourth-boundary-process-type-only",
        "apf2k8-v1:98403d88:1ad60880:981a5714:cde5b922:"
        "fifth-boundary-critical-section-only")
    source = source.replace("UINT64_C(0xA2F24008D90890C4)",
                            "UINT64_C(0xA2F25009D9549585)")
    source = source.replace("constexpr std::uint32_t kMagic = 0x41504635u;",
                            "constexpr std::uint32_t kMagic = 0x41504636u;")
    constants = "constexpr std::uint32_t kExpectedFourthReturn = 0x84BED90Cu;\n"
    require(source.count(constants) == 1, "fifth harness constants changed")
    source = source.replace(constants, constants + r'''constexpr std::uint32_t kExpectedFifthThunk = 0x84D07FBCu;
constexpr std::uint32_t kExpectedFifthCall = 0x84BED954u;
constexpr std::uint32_t kExpectedFifthReturn = 0x84BED958u;
constexpr std::uint32_t kExpectedFifthArgument = 0x40000610u;
''', 1)

    helper_start = source.index("bool initialized_page_exact(")
    helper_end = source.index("\nstd::int64_t monotonic_milliseconds()", helper_start)
    helper = r'''bool initialized_page_exact(const std::uint8_t *bytes) {
    std::size_t nonzero = 0u;
    for (std::size_t index = 0u; index < 0x10000u; ++index) {
        if (bytes[index] != 0u) ++nonzero;
    }
    if (nonzero != 811u || load_be_u32(bytes + 16u) != 0xEEFFEEFFu ||
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
    return load_be_u32(bytes + 0x600u) == 0u &&
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

    catch_old = (
        "report.outcome = stop.import_thunk == kExpectedFourthThunk\n"
        "                             ? child_outcome::expected_fifth_boundary\n"
    )
    catch_new = (
        "report.outcome = stop.import_thunk == kExpectedFifthThunk\n"
        "                             ? child_outcome::expected_fifth_boundary\n"
    )
    require(source.count(catch_old) == 1, "fifth harness catch gate changed")
    source = source.replace(catch_old, catch_new, 1)

    expected_start = source.index("    const bool expected =\n")
    expected_end = source.index(
        "\n    vc_apf_guest_instruction_budget_unbind();", expected_start)
    expected = r'''    const bool expected =
        report.outcome == child_outcome::expected_fifth_boundary &&
        report.gate_status == VC_APF_FIRST_ENTRY_OK &&
        report.adapter_status == VC_APF_BOOT_LEAF_OK &&
        report.import_thunk == kExpectedFifthThunk &&
        report.instructions_consumed == 1019u &&
        report.function_dispatches_consumed == 5u &&
        report.trace_count == 1019u &&
        report.last_guest_address == kExpectedFifthCall &&
        report.context_lr == kExpectedFifthReturn &&
        report.context_r3 == kExpectedFifthArgument &&
        report.bridge.stage == 5u &&
        report.bridge.first_instruction_count == 38u &&
        report.bridge.second_instruction_count == 264u &&
        report.bridge.third_instruction_count == 283u &&
        report.bridge.fourth_instruction_count == 365u &&
        report.bridge.fourth_thunk == kExpectedFourthThunk &&
        report.bridge.fourth_lr == kExpectedFourthReturn &&
        report.bridge.fourth_r3_output == 1u &&
        report.bridge.fifth_thunk == kExpectedFifthThunk &&
        report.bridge.fifth_lr == kExpectedFifthReturn &&
        report.bridge.fifth_r3_input == kExpectedFifthArgument &&
        report.bridge.fifth_r3_output == kExpectedFifthArgument &&
        report.bridge.fifth_r21_input == kExpectedFifthArgument &&
        report.bridge.fifth_r29_input == kExpectedFifthArgument &&
        report.bridge.fifth_instruction_count == 1019u &&
        report.bridge.fifth_vm_ledger_exact_before_adapter == 1u &&
        report.bridge.fifth_page_exact_before_adapter == 1u &&
        report.bridge.fifth_global_flags_before_adapter == 0u &&
        report.bridge.fifth_backing_fnv_before_adapter ==
            UINT64_C(0xF663B4BBF571B2AD) &&
        report.bridge.fifth_critical_section_exact_after_adapter == 1u &&
        report.bridge.fifth_backing_fnv_after_adapter ==
            UINT64_C(0xD0D16B728ECA1764) &&
        report.vm_page_count == 4096u &&
        report.vm_allocation_count == 1u &&
        report.reserved_page_count == 15u &&
        report.committed_page_count == 1u &&
        report.vm_ledger_exact == 1u &&
        report.initialized_page_exact == 1u &&
        report.remaining_backing_pattern_exact == 1u &&
        report.backing_fnv_before == UINT64_C(0x1F5E0DF9BC822325) &&
        report.backing_fnv_after == UINT64_C(0xD0D16B728ECA1764);
    if (report.outcome == child_outcome::expected_fifth_boundary &&
        !expected) {
        report.outcome = child_outcome::unexpected_exception;
    }
'''
    source = source[:expected_start] + expected + source[expected_end:]

    print_start_marker = (
        '    std::printf(\n'
        '        "APF_GUARDED_FIFTH_BOUNDARY_CHILD_RESULT outcome=%s signal=0 "'
    )
    print_start = source.index(print_start_marker)
    print_end = source.index(
        "    for (std::uint32_t index = 0u; index < report.trace_count; ++index)",
        print_start)
    print_block = r'''    std::printf(
        "APF_GUARDED_FIFTH_BOUNDARY_CHILD_RESULT outcome=%s signal=0 "
        "entry_authorized=%u entry_called=%u prerequisite_step=%u "
        "gate_status=%u adapter_status=%u thunk=0x%08X stage=%u "
        "instructions=%llu function_dispatches=%llu last_pc=0x%08X "
        "lr=0x%08X r3=0x%08X first_instructions=%u "
        "second_instructions=%u third_instructions=%u "
        "fourth_instructions=%u fourth_thunk=0x%08X fourth_lr=0x%08X "
        "fourth_r3_out=0x%08X fifth_instructions=%u "
        "fifth_thunk=0x%08X fifth_lr=0x%08X fifth_r3_in=0x%08X "
        "fifth_r3_out=0x%08X fifth_r21=0x%08X fifth_r29=0x%08X "
        "fifth_ledger=%u fifth_page=%u fifth_global=0x%08X "
        "fifth_fnv_before=0x%016llX fifth_cs_exact=%u "
        "fifth_fnv_after=0x%016llX vm_pages=%u vm_allocations=%u "
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
        report.bridge.fourth_thunk, report.bridge.fourth_lr,
        report.bridge.fourth_r3_output,
        report.bridge.fifth_instruction_count,
        report.bridge.fifth_thunk, report.bridge.fifth_lr,
        report.bridge.fifth_r3_input, report.bridge.fifth_r3_output,
        report.bridge.fifth_r21_input, report.bridge.fifth_r29_input,
        report.bridge.fifth_vm_ledger_exact_before_adapter,
        report.bridge.fifth_page_exact_before_adapter,
        report.bridge.fifth_global_flags_before_adapter,
        static_cast<unsigned long long>(
            report.bridge.fifth_backing_fnv_before_adapter),
        report.bridge.fifth_critical_section_exact_after_adapter,
        static_cast<unsigned long long>(
            report.bridge.fifth_backing_fnv_after_adapter),
        report.vm_page_count, report.vm_allocation_count,
        report.reserved_page_count, report.committed_page_count,
        report.vm_ledger_exact, report.initialized_page_exact,
        report.remaining_backing_pattern_exact,
        static_cast<unsigned long long>(report.backing_fnv_before),
        static_cast<unsigned long long>(report.backing_fnv_after));
'''
    return source[:print_start] + print_block + source[print_end:]


def parse_result_line(line: str) -> dict[str, str]:
    require(line.startswith(RESULT_PREFIX), "fifth result prefix changed")
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
    fourth_report_path = root / (
        "reports/static_recomp/apf2k8_guarded_fourth_boundary_execution.json")
    static_path = root / (
        "reports/static_recomp/apf2k8_post_process_type_static.json")
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
    fourth_driver_path = root / "tools/apf_guarded_fourth_boundary_execute.py"
    static_analyzer_path = root / "tools/apf_post_process_type_static.py"
    clang = shutil.which(args.clang)
    clangxx = shutil.which(args.clangxx)
    required = [
        decoded, xex, volume, fourth_report_path, static_path,
        composed_report_path, budget_report_path, leaf_report_path,
        xex_report_path, first_bridge_path, budget_source_path,
        fourth_driver_path, static_analyzer_path,
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "src/static_runtime/apf_boot_leaf_adapters.c",
    ]
    require(args.jobs > 0 and clang is not None and clangxx is not None and
            all(path.is_file() and not path.is_symlink() for path in required),
            "fifth-boundary prerequisite missing")
    require(sha256_file(xex) == EXPECTED_XEX_SHA256 and
            sha256_file(volume) == EXPECTED_VOLUME_SHA256 and
            decoded.stat().st_size == EXPECTED_DECODED_SIZE and
            sha256_file(decoded) == EXPECTED_DECODED_SHA256,
            "retail or decoded APF input changed")
    require(sha256_file(fourth_report_path) ==
                EXPECTED_FOURTH_REPORT_SHA256 and
            sha256_file(static_path) == EXPECTED_POST_PROCESS_STATIC_SHA256 and
            sha256_file(fourth_driver_path) ==
                EXPECTED_FOURTH_DRIVER_SHA256 and
            sha256_file(static_analyzer_path) ==
                EXPECTED_POST_PROCESS_ANALYZER_SHA256 and
            sha256_file(first_bridge_path) == EXPECTED_FIRST_BRIDGE_SHA256 and
            sha256_file(budget_source_path) == EXPECTED_BUDGET_SOURCE_SHA256 and
            sha256_file(leaf_report_path) == EXPECTED_LEAF_REPORT_SHA256 and
            sha256_file(composed_report_path) ==
                EXPECTED_COMPOSED_REPORT_SHA256 and
            sha256_file(budget_report_path) == EXPECTED_BUDGET_REPORT_SHA256,
            "pinned APF evidence changed")

    prior = json.loads(fourth_report_path.read_text(encoding="utf-8"))
    static = json.loads(static_path.read_text(encoding="utf-8"))
    require(prior["result"]["child_outcome"] ==
                "expected_fourth_boundary" and
            prior["generated_execution"]["executed_guest_instruction_count"] ==
                365 and
            static["schema"] == "apf2k8_post_process_type_static/v1" and
            static["static_trace"][
                "continuation_instruction_count_through_next_call"] == 654 and
            static["static_trace"][
                "cumulative_instruction_count_through_next_call"] == 1019 and
            static["static_trace"]["ordered_pc_sha256"] ==
                EXPECTED_CONTINUATION_TRACE_SHA256 and
            static["next_boundary"]["call_pc"] == "0x84BED954" and
            static["next_boundary"]["return_pc"] == "0x84BED958" and
            static["next_boundary"]["thunk"] == "0x84D07FBC",
            "fifth static or dynamic prerequisite changed")

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
    with tempfile.TemporaryDirectory(prefix="apf-fifth-boundary-v1-",
                                     dir=temp_root) as temporary:
        build = Path(temporary)
        files = {
            "abort": build / "nonfrontier_abort.h",
            "stubs": build / "nonfrontier_imports.cpp",
            "evidence": build / "fifth_boundary_evidence.h",
            "bridge": build / "fifth_boundary_bridge.cpp",
            "budget": build / "fifth_boundary_budget.cpp",
            "harness": build / "guarded_fifth_driver.cpp",
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
        require(not failures, "fifth-boundary compilation failed: " +
                " | ".join(item["stderr"][-2000:] for item in failures[:3]))
        executable = build / "apf_guarded_fifth_boundary_v1"
        linked = subprocess.run([
            clangxx, "-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie",
            *[str(target) for _, target in specs], "-lm", "-o", str(executable),
        ], capture_output=True, text=True, check=False)
        require(linked.returncode == 0,
                "fifth-boundary link failed: " + linked.stderr[-2400:])
        executed = subprocess.run([
            str(executable), str(decoded), str(xex), AUTHORIZATION_TOKEN,
        ], capture_output=True, text=True, check=False, timeout=30)
        require(executed.returncode == 0,
                f"fifth child changed ({executed.returncode}): " +
                executed.stdout[-5000:] + executed.stderr[-2400:])
        lines = [line for line in executed.stdout.splitlines()
                 if line.startswith(RESULT_PREFIX)]
        require(len(lines) == 1 and executed.stderr == "",
                "fifth child transcript changed")
        result_line = lines[0]
        fields = parse_result_line(result_line)

    exact = {
        "outcome": "expected_fifth_boundary", "signal": "0",
        "entry_authorized": "1", "entry_called": "1",
        "prerequisite_step": "6", "gate_status": "0",
        "adapter_status": "0", "stage": "5", "instructions": "1019",
        "function_dispatches": "5", "first_instructions": "38",
        "second_instructions": "264", "third_instructions": "283",
        "fourth_instructions": "365", "fifth_instructions": "1019",
        "fifth_ledger": "1", "fifth_page": "1", "fifth_cs_exact": "1",
        "reserved_pages": "15", "committed_pages": "1",
        "ledger_exact": "1", "initialized_page_exact": "1",
        "remaining_pattern_exact": "1", "containment_normal": "1",
        "containment_signal": "1", "containment_timeout": "1",
    }
    require(all(fields.get(key) == value for key, value in exact.items()),
            "fifth result scalar changed")
    expected_hex = {
        "thunk": EXPECTED_FIFTH_THUNK,
        "last_pc": EXPECTED_FIFTH_CALL,
        "lr": EXPECTED_FIFTH_RETURN,
        "r3": EXPECTED_FIFTH_ARGUMENT,
        "fourth_thunk": fourth.EXPECTED_FOURTH_THUNK,
        "fourth_lr": fourth.EXPECTED_FOURTH_RETURN,
        "fourth_r3_out": 1,
        "fifth_thunk": EXPECTED_FIFTH_THUNK,
        "fifth_lr": EXPECTED_FIFTH_RETURN,
        "fifth_r3_in": EXPECTED_FIFTH_ARGUMENT,
        "fifth_r3_out": EXPECTED_FIFTH_ARGUMENT,
        "fifth_r21": EXPECTED_FIFTH_ARGUMENT,
        "fifth_r29": EXPECTED_FIFTH_ARGUMENT,
        "fifth_global": 0,
        "fifth_fnv_before": EXPECTED_PRE_FIFTH_BACKING_FNV,
        "fifth_fnv_after": EXPECTED_POST_FIFTH_BACKING_FNV,
        "backing_fnv_before": 0x1F5E0DF9BC822325,
        "backing_fnv_after": EXPECTED_POST_FIFTH_BACKING_FNV,
    }
    require(all(int(fields.get(key, "-1"), 0) == value
                for key, value in expected_hex.items()),
            "fifth ABI/state changed")
    trace = [int(value, 16) for value in fields["trace"].split(",") if value]
    require(len(trace) == EXPECTED_CUMULATIVE_INSTRUCTIONS and
            trace[364] == fourth.EXPECTED_FOURTH_CALL and
            trace[365] == fourth.EXPECTED_FOURTH_RETURN and
            trace[-1] == EXPECTED_FIFTH_CALL,
            "fifth dynamic trace endpoints changed")
    continuation = trace[365:]
    continuation_sha = trace_sha256(continuation)
    require(len(continuation) == EXPECTED_CONTINUATION_INSTRUCTIONS and
            continuation_sha == EXPECTED_CONTINUATION_TRACE_SHA256 ==
                static["static_trace"]["ordered_pc_sha256"],
            "fifth dynamic/static trace mismatch")

    local_files = [
        first_bridge_path, budget_source_path,
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "src/static_runtime/apf_boot_leaf_adapters.c",
        fourth_driver_path, static_analyzer_path,
        root / "tools/apf_guarded_fifth_boundary_execute.py",
    ]
    report = {
        "schema": SCHEMA,
        "result": {
            "guarded_fourth_boundary_execution_revalidated": True,
            "post_process_type_static_proof_revalidated": True,
            "translated_title_code_executed": True,
            "continued_past_fourth_typed_boundary": True,
            "expected_fifth_typed_boundary_reached": True,
            "fifth_typed_adapter_completed": True,
            "continued_past_fifth_typed_boundary": False,
            "child_outcome": fields["outcome"],
            "signal_number": 0,
            "native_boot_proved": False,
            "main_menu_proved": False,
        },
        "authorization_gates": {
            "retail_xex_sha256_exact": True,
            "retail_volume_sha256_exact": True,
            "decoded_image_sha256_and_size_exact": True,
            "guarded_fourth_report_exact": True,
            "post_process_type_static_report_exact": True,
            "composed_and_instrumented_complete_trees_exact": True,
            "instruction_hook_count": hook_count,
            "mapping_count": mapping_count,
            "typed_import_count": len(typed_imports),
            "fifth_dynamic_pc_lr_register_page_state_gate": True,
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
            "post_process_type_ordered_pc_sha256": continuation_sha,
            "ordered_guest_pcs": [f"0x{pc:08X}" for pc in trace],
            "fifth_boundary": {
                "import": "RtlInitializeCriticalSection",
                "call_pc": f"0x{EXPECTED_FIFTH_CALL:08X}",
                "return_pc": f"0x{EXPECTED_FIFTH_RETURN:08X}",
                "thunk": f"0x{EXPECTED_FIFTH_THUNK:08X}",
                "instruction_count_at_call": len(trace),
                "arguments": {
                    "r3_critical_section": fields["fifth_r3_in"],
                },
                "r21_allocator_cursor": fields["fifth_r21"],
                "r29_allocator_cursor": fields["fifth_r29"],
                "adapter_status": "ok",
                "critical_section_initialized_exact": True,
                "generated_return_instruction_executed": False,
                "terminal_semantics": (
                    "existing typed critical-section adapter completed; "
                    "bridge threw before generated instruction 0x84BED958"
                ),
            },
        },
        "virtual_memory_and_initialization": {
            "active_allocation_count": 1,
            "allocation_page_count": 16,
            "committed_page_count": 1,
            "remaining_reserved_page_count": 15,
            "vm_ledger_exact": True,
            "process_type_byte": "0x01",
            "allocator_list_head_count": 128,
            "pre_adapter_page_sha256": EXPECTED_PRE_FIFTH_PAGE_SHA256,
            "pre_adapter_nonzero_byte_count": 799,
            "pre_adapter_allocation_fnv1a64": fields["fifth_fnv_before"],
            "critical_section_address": "0x40000610",
            "critical_section_size": 28,
            "post_adapter_page_sha256": EXPECTED_POST_FIFTH_PAGE_SHA256,
            "post_adapter_nonzero_byte_count": 811,
            "post_adapter_allocation_fnv1a64": fields["fifth_fnv_after"],
            "remaining_15_page_pattern_exact": True,
        },
        "inputs": {
            "retail_xex": pin(xex, root),
            "retail_volume": pin(volume, root),
            "decoded_image": {
                "size": decoded.stat().st_size,
                "sha256": sha256_file(decoded),
                "temporary_validator_artifact": True,
            },
            "guarded_fourth_report": pin(fourth_report_path, root),
            "post_process_type_static_report": pin(static_path, root),
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
            "// PORTME at 0x84BED958: statically prove and type the next exact boundary before authorizing any further generated instruction.",
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
        "APF_GUARDED_FIFTH_BOUNDARY_EXECUTION_PASS instructions=1019 "
        "function_dispatches=5 fifth=0x84BED954 critical_section=0x40000610 "
        "committed_pages=1 reserved_pages=15 continued_after_fifth=0 "
        "native_boot=0 temporary_outputs_deleted=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
