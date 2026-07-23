#!/usr/bin/env python3
"""Execute APF's generated entry only to its first typed import boundary.

This driver is intentionally separate from the normal Linux host shell.  It
revalidates the two completed source gates, exact retail/decoded inputs, and
the previous first-entry readiness evidence before it compiles a throwaway
instrumented runtime.  That executable performs containment self-tests, forks
one bounded child, and only that child may call generated ``_xstart``.
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
from typing import Any, Iterable


SCHEMA = "apf2k8_guarded_first_entry_execution/v2"
EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_VOLUME_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_DECODED_SIZE = 0x03380000
EXPECTED_COMPOSED_REPORT_SHA256 = (
    "4e15f16f06263dc48279f5e59d9019345d915dc74e2ac8306d9795f5f37518b1"
)
EXPECTED_BUDGET_REPORT_SHA256 = (
    "c483b941702e82d984bc4c1e64a9fa6772eca15197f411d2b148a54b3aa65e7f"
)
EXPECTED_READINESS_REPORT_SHA256 = (
    "fbd8c00557e95f2ea8fda0b5f2aaf1c38c345f7be1232e390a796066a896b078"
)
EXPECTED_COMPOSED_TREE_SHA256 = (
    "33bd100b5a7b358dd651b4c55ace6b41c73f9d3552a6684cede299ae9ac9532f"
)
EXPECTED_INSTRUMENTED_TREE_SHA256 = (
    "cf32ecfc343e4b7ad8573d5935c6bbdbe435e2b6d8a75610f468de0b435b1def"
)
EXPECTED_HOOK_MANIFEST_SHA256 = (
    "e6feaf772baf701a84164a7cae4904b40f539888d2a8f37960445431f8545a4c"
)
EXPECTED_NUMBERED_COUNT = 236
EXPECTED_CPP_COUNT = 237
EXPECTED_MAPPING_COUNT = 60_731
EXPECTED_IMPLEMENTATION_COUNT = 60_397
EXPECTED_HOOK_COUNT = 1_808_124
EXPECTED_IMPORT_COUNT = 334
EXPECTED_TYPED_IMPORT_COUNT = 30
EXPECTED_ENTRY = 0x84BE9D08
EXPECTED_FIRST_CALL = 0x84BF1888
EXPECTED_FIRST_RETURN = 0x84BF188C
EXPECTED_FIRST_THUNK = 0x84D0859C
AUTHORIZATION_TOKEN = (
    "apf2k8-v2:33bd100b:cf32ecfc:981a5714:cde5b922:first-boundary-only"
)
RESULT_PREFIX = "APF_GUARDED_FIRST_ENTRY_CHILD_RESULT "


class GuardedExecutionError(RuntimeError):
    """Raised when an authorization or contained-execution invariant fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GuardedExecutionError(message)


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def exact_roster(directory: Path) -> list[Path]:
    names = {
        "ppc_config.h", "ppc_context.h", "ppc_recomp_shared.h",
        "ppc_func_mapping.cpp",
        *(f"ppc_recomp.{index}.cpp"
          for index in range(EXPECTED_NUMBERED_COUNT)),
    }
    require(directory.is_dir(), f"generated corpus is missing: {directory}")
    actual = sorted(directory.iterdir(), key=lambda item: item.name)
    require(all(path.is_file() and not path.is_symlink() for path in actual),
            f"generated corpus has a non-regular/symlink entry: {directory}")
    require({path.name for path in actual} == names,
            f"generated corpus roster changed: {directory}")
    return actual


def composed_tree_sha256(roster: Iterable[Path]) -> str:
    state = hashlib.sha256()
    for path in sorted(roster, key=lambda item: item.name):
        size = path.stat().st_size
        digest = sha256_file(path)
        state.update(path.name.encode("utf-8") + b"\0")
        state.update(size.to_bytes(8, "big"))
        state.update(bytes.fromhex(digest))
    return state.hexdigest()


def budget_tree_sha256(directory: Path, roster: Iterable[Path]) -> str:
    state = hashlib.sha256()
    for path in sorted(roster, key=lambda item: item.name):
        name = path.relative_to(directory).as_posix().encode("utf-8")
        data = path.read_bytes()
        state.update(len(name).to_bytes(4, "big"))
        state.update(name)
        state.update(len(data).to_bytes(8, "big"))
        state.update(data)
    return state.hexdigest()


def pin(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": relative(path, root),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def compile_one(command: list[str], output: Path) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True,
                               check=False)
    return {
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output": output,
    }


def nonfrontier_header_source() -> str:
    return """#pragma once
#include <cstdint>
struct vc_apf_nonfrontier_import_abort {
    std::uint32_t import_index;
};
"""


def nonfrontier_stub_source(import_names: list[str]) -> str:
    lines = [
        '#include "ppc_recomp_shared.h"\n',
        '#include "nonfrontier_abort.h"\n\n',
        "// PORTME: replace each abort boundary with exact guest-ABI semantics.\n",
        "#define APF_NONFRONTIER_IMPORT(symbol, index) \\\n    PPC_FUNC(symbol) { (void)ctx; (void)base; "
        "throw vc_apf_nonfrontier_import_abort{index}; }\n\n",
    ]
    lines.extend(
        f"APF_NONFRONTIER_IMPORT({name}, {index}u)\n"
        for index, name in enumerate(import_names)
    )
    lines.append("#undef APF_NONFRONTIER_IMPORT\n")
    return "".join(lines)


def harness_source() -> str:
    return r'''#include "ppc_recomp_shared.h"
#include "nonfrontier_abort.h"
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
    "apf2k8-v2:33bd100b:cf32ecfc:981a5714:cde5b922:first-boundary-only";
constexpr std::uint32_t kMagic = 0x41504632u;
constexpr std::uint32_t kInstructionLimit = 4096u;
constexpr std::uint32_t kFunctionDispatchLimit = 64u;

enum class child_outcome : std::uint32_t {
    expected_typed_boundary = 1,
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
    std::uint32_t recent_count;
    std::uint64_t instructions_consumed;
    std::uint64_t function_dispatches_consumed;
    std::uint32_t recent_addresses[VC_APF_GUEST_INSTRUCTION_TRACE_CAPACITY];
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

std::int64_t monotonic_milliseconds() {
    struct timespec now{};
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return -1;
    return static_cast<std::int64_t>(now.tv_sec) * 1000 +
           now.tv_nsec / 1000000;
}

int containment_normal(void *) { return 0x4A51; }
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
        result.callback_result != 0x4A51) return false;
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
    vc_apf_guest_instruction_trace trace{};
    report.instructions_consumed = state.budget.instructions_consumed;
    report.function_dispatches_consumed =
        state.budget.function_dispatches_consumed;
    report.context_lr = static_cast<std::uint32_t>(context.lr);
    report.context_r3 = context.r3.u32;
    if (vc_apf_guest_instruction_budget_snapshot(&trace) ==
        VC_APF_FIRST_ENTRY_OK) {
        report.recent_count = trace.recent_count;
        for (std::uint32_t index = 0u; index < trace.recent_count; ++index) {
            report.recent_addresses[index] = trace.recent_addresses[index];
        }
        if (trace.recent_count != 0u) {
            report.last_guest_address =
                trace.recent_addresses[trace.recent_count - 1u];
        }
    }
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
    if (!state.prepared ||
        state.guest_address_space_byte_count !=
            VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE ||
        state.imported_data.seeded_slot_count != 2u ||
        state.imported_data.preserved_ordinal_slot_count != 11u ||
        !state.imported_data_evidence.sub_84bf1850_reaches_header_query ||
        state.imported_data_evidence.requested_key_present ||
        !state.imported_data_evidence.bounded_absent_key_result_is_null ||
        state.imported_data_evidence.callback_dispatch_possible) {
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
            __imp__RtlImageXexHeaderField) {
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
            VC_APF_FIRST_ENTRY_OK) {
        vc_apf_first_entry_xenon_bridge_unbind();
        vc_apf_first_entry_destroy(&state);
        write_report_and_exit(descriptor, report);
    }

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
        report.outcome = child_outcome::expected_typed_boundary;
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

    const bool expected =
        report.outcome == child_outcome::expected_typed_boundary &&
        report.gate_status == VC_APF_FIRST_ENTRY_OK &&
        report.adapter_status == VC_APF_BOOT_LEAF_OK &&
        report.import_thunk == VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK &&
        state.first_boundary_thunk == VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK &&
        state.first_boundary_adapter_status == VC_APF_BOOT_LEAF_OK &&
        report.instructions_consumed > 0u &&
        report.instructions_consumed < kInstructionLimit &&
        report.function_dispatches_consumed == 1u &&
        report.last_guest_address == VC_APF_FIRST_ENTRY_FIRST_IMPORT_CALL &&
        report.context_lr == VC_APF_FIRST_ENTRY_FIRST_IMPORT_RETURN &&
        report.context_r3 == 0u;
    if (report.outcome == child_outcome::expected_typed_boundary && !expected) {
        report.outcome = child_outcome::unexpected_exception;
    }

    vc_apf_guest_instruction_budget_unbind();
    vc_apf_first_entry_xenon_bridge_unbind();
    vc_apf_first_entry_destroy(&state);
    write_report_and_exit(descriptor, report);
}

const char *outcome_name(child_outcome outcome) {
    switch (outcome) {
    case child_outcome::expected_typed_boundary: return "expected_typed_boundary";
    case child_outcome::instruction_budget_exhausted: return "budget_exhaustion";
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
        std::printf("APF_GUARDED_FIRST_ENTRY_CHILD_RESULT outcome=timeout "
                    "signal=%d containment_normal=1 containment_signal=1 "
                    "containment_timeout=1\n", SIGKILL);
        return 20;
    }
    if (WIFSIGNALED(wait_status)) {
        std::printf("APF_GUARDED_FIRST_ENTRY_CHILD_RESULT outcome=signal "
                    "signal=%d containment_normal=1 containment_signal=1 "
                    "containment_timeout=1\n", WTERMSIG(wait_status));
        return 21;
    }
    if (!WIFEXITED(wait_status) || WEXITSTATUS(wait_status) != 0 ||
        received != sizeof(report) || report.magic != kMagic) {
        std::printf("APF_GUARDED_FIRST_ENTRY_CHILD_RESULT outcome=import_abort "
                    "signal=0 containment_normal=1 containment_signal=1 "
                    "containment_timeout=1 report_missing=1\n");
        return 22;
    }

    std::printf("APF_GUARDED_FIRST_ENTRY_CHILD_RESULT outcome=%s signal=0 "
                "entry_authorized=%u entry_called=%u prerequisite_step=%u "
                "gate_status=%u adapter_status=%u thunk=0x%08X "
                "instructions=%llu function_dispatches=%llu "
                "last_pc=0x%08X lr=0x%08X r3=0x%08X recent=",
                outcome_name(report.outcome), report.entry_authorized,
                report.entry_called, report.prerequisite_step,
                report.gate_status, report.adapter_status,
                report.import_thunk,
                static_cast<unsigned long long>(report.instructions_consumed),
                static_cast<unsigned long long>(
                    report.function_dispatches_consumed),
                report.last_guest_address, report.context_lr,
                report.context_r3);
    for (std::uint32_t index = 0u; index < report.recent_count; ++index) {
        std::printf("%s%08X", index == 0u ? "" : ",",
                    report.recent_addresses[index]);
    }
    std::printf(" containment_normal=1 containment_signal=1 "
                "containment_timeout=1\n");
    return report.outcome == child_outcome::expected_typed_boundary ? 0 : 23;
}
'''


def parse_result_line(line: str) -> dict[str, str]:
    require(line.startswith(RESULT_PREFIX), "guarded result prefix changed")
    fields: dict[str, str] = {}
    for token in line[len(RESULT_PREFIX):].split():
        require("=" in token, f"malformed guarded result token: {token}")
        key, value = token.split("=", 1)
        require(key not in fields, f"duplicate guarded result field: {key}")
        fields[key] = value
    return fields


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
    parser.add_argument("--readiness-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_first_entry_readiness.json"))
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
    readiness_report_path = resolve(args.readiness_report)
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

    required_files = [
        composed_report_path, budget_report_path, readiness_report_path,
        xex_report_path, xex, volume, decoded,
        root / "include/static_runtime/apf_first_entry_gate.h",
        root / "include/static_runtime/apf_first_entry_xenon_bridge.h",
        root / "include/static_runtime/apf_guest_instruction_budget.h",
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "src/static_runtime/apf_first_entry_xenon_bridge.cpp",
        root / "src/static_runtime/apf_guest_instruction_budget.cpp",
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "src/static_runtime/apf_boot_leaf_adapters.c",
    ]
    require(all(path.is_file() and not path.is_symlink()
                for path in required_files), "guarded-entry input is missing")
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
    require(sha256_file(readiness_report_path) ==
            EXPECTED_READINESS_REPORT_SHA256,
            "v1 first-entry readiness report hash changed")

    composed_report = json.loads(
        composed_report_path.read_text(encoding="utf-8"))
    budget_report = json.loads(budget_report_path.read_text(encoding="utf-8"))
    readiness_report = json.loads(
        readiness_report_path.read_text(encoding="utf-8"))
    require(composed_report["schema"] ==
            "apf2k8_static_recomp_opcode_switch_composed/v1" and
            composed_report["result"]["composed_derived_corpus_blocker_resolved"]
            is True and
            composed_report["result"]["single_composed_derived_corpus_exists"]
            is True and
            composed_report["result"]["unrecognized_instruction_count"] == 0 and
            composed_report["generated_corpus"][
                "generated_implementation_count"] ==
            EXPECTED_IMPLEMENTATION_COUNT and
            composed_report["generated_corpus"][
                "cpp_translation_unit_count"] == EXPECTED_CPP_COUNT,
            "composed-corpus gate is not resolved")
    require(budget_report["schema"] ==
            "apf2k8_guest_instruction_budget_instrumentation/v1" and
            budget_report["result"][
                "instruction_budget_blocker_resolved_for_derived_corpus"]
            is True and
            budget_report["result"]["instrumented_hook_count"] ==
            EXPECTED_HOOK_COUNT and
            budget_report["result"]["uninstrumentable_construct_count"] == 0,
            "instruction-budget gate is not resolved")
    require(readiness_report["schema"] ==
            "apf2k8_first_entry_readiness/v1" and
            [item["code"] for item in readiness_report["ordered_blockers"]] ==
            ["COMPOSED_DERIVED_CORPUS",
             "INSTRUCTION_BUDGET_INSTRUMENTATION"] and
            readiness_report["result"]["exact_first_typed_boundary_proved"]
            is True and
            readiness_report["result"]["preboundary_unresolved_indirect_sites"]
            == 0,
            "v1 readiness evidence changed")
    for item in readiness_report["inputs"]["local_files"]:
        readiness_local = root / item["path"]
        require(readiness_local.is_file() and
                readiness_local.stat().st_size == item.get(
                    "size", readiness_local.stat().st_size) and
                sha256_file(readiness_local) == item["sha256"],
                f"v1 readiness pinned file changed: {item['path']}")

    composed_roster = exact_roster(composed)
    generated_roster = exact_roster(generated)
    declared_files = {
        item["name"]: item for item in
        composed_report["generated_corpus"]["files"]
    }
    require(len(declared_files) == len(composed_roster) == 240,
            "composed file manifest count changed")
    for path in composed_roster:
        item = declared_files.get(path.name)
        require(item is not None and item["size"] == path.stat().st_size and
                item["sha256"] == sha256_file(path),
                f"composed file manifest mismatch: {path.name}")
    composed_tree = composed_tree_sha256(composed_roster)
    instrumented_tree = budget_tree_sha256(generated, generated_roster)
    require(composed_tree == EXPECTED_COMPOSED_TREE_SHA256 ==
            composed_report["generated_corpus"]["tree_sha256"],
            "composed tree hash changed")
    require(instrumented_tree == EXPECTED_INSTRUMENTED_TREE_SHA256 ==
            budget_report["output"]["tree_sha256"],
            "instrumented tree hash changed")
    budget_rows = {item["path"]: item for item in budget_report["files"]}
    require(len(budget_rows) == EXPECTED_NUMBERED_COUNT,
            "budget per-TU manifest count changed")
    numbered = [generated / f"ppc_recomp.{index}.cpp"
                for index in range(EXPECTED_NUMBERED_COUNT)]
    for path in numbered:
        require(budget_rows[path.name]["instrumented_sha256"] ==
                sha256_file(path),
                f"instrumented TU hash changed: {path.name}")
    require(budget_report["coverage_proof"]["hook_manifest_sha256"] ==
            EXPECTED_HOOK_MANIFEST_SHA256 and
            budget_report["coverage_proof"]["marker_manifest_sha256"] ==
            EXPECTED_HOOK_MANIFEST_SHA256,
            "instruction hook/marker manifest changed")
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
            "generated dispatch mapping/entry changed")

    xex_report = json.loads(xex_report_path.read_text(encoding="utf-8"))
    all_imports = {
        "__imp__" + item["name"] for item in xex_report["imports"]["items"]
        if item["thunk_address"] is not None
    }
    bridge_text = (root / "src/static_runtime/"
                   "apf_first_entry_xenon_bridge.cpp").read_text(
                       encoding="utf-8")
    typed_imports = set(re.findall(
        r"^VC_APF_DEFINE_IMPORT\((__imp__[A-Za-z0-9_]+),",
        bridge_text, re.MULTILINE))
    require(len(all_imports) == EXPECTED_IMPORT_COUNT and
            len(typed_imports) == EXPECTED_TYPED_IMPORT_COUNT and
            typed_imports < all_imports,
            "typed/nonfrontier import split changed")
    nonfrontier_imports = sorted(all_imports - typed_imports)

    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apf-guarded-entry-v2-",
                                     dir=temp_root) as temporary:
        build = Path(temporary)
        abort_header = build / "nonfrontier_abort.h"
        stubs = build / "nonfrontier_imports.cpp"
        harness = build / "guarded_driver.cpp"
        abort_header.write_text(nonfrontier_header_source(), encoding="utf-8")
        stubs.write_text(nonfrontier_stub_source(nonfrontier_imports),
                         encoding="utf-8")
        harness.write_text(harness_source(), encoding="utf-8")

        generated_sources = [generated / "ppc_func_mapping.cpp", *numbered]
        cpp_sources = [
            *generated_sources,
            root / "src/static_runtime/apf_first_entry_xenon_bridge.cpp",
            root / "src/static_runtime/apf_guest_instruction_budget.cpp",
            stubs, harness,
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
                executor.submit(compile_one, command, output): output
                for command, output in compile_specs
            }
            for future in as_completed(futures):
                outcomes.append(future.result())
        failures = [item for item in outcomes if item["return_code"] != 0]
        require(not failures, "guarded object compilation failed: " +
                " | ".join(item["stderr"][-1200:]
                           for item in failures[:3]))
        require(all(item["output"].is_file() for item in outcomes),
                "guarded compiled object is missing")

        executable = build / "apf_guarded_first_entry_v2"
        objects = [output for _, output in compile_specs]
        linked = subprocess.run([
            clangxx, "-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie",
            *map(str, objects), "-lm", "-o", str(executable),
        ], capture_output=True, text=True, check=False)
        require(linked.returncode == 0,
                "guarded runtime link failed: " + linked.stderr[-1800:])
        executed = subprocess.run([
            str(executable), str(decoded), str(xex), AUTHORIZATION_TOKEN,
        ], capture_output=True, text=True, check=False, timeout=30)
        require(executed.returncode == 0,
                f"guarded child terminal was not expected "
                f"({executed.returncode}): {executed.stdout[-1200:]} "
                f"{executed.stderr[-1200:]}")
        lines = [line for line in executed.stdout.splitlines()
                 if line.startswith(RESULT_PREFIX)]
        require(len(lines) == 1 and executed.stderr == "",
                "guarded child transcript changed")
        result_line = lines[0]
        fields = parse_result_line(result_line)
        require(fields.get("outcome") == "expected_typed_boundary" and
                fields.get("signal") == "0" and
                fields.get("entry_authorized") == "1" and
                fields.get("entry_called") == "1" and
                fields.get("prerequisite_step") == "6" and
                fields.get("gate_status") == "0" and
                fields.get("adapter_status") == "0" and
                int(fields.get("thunk", "0"), 0) == EXPECTED_FIRST_THUNK and
                int(fields.get("last_pc", "0"), 0) == EXPECTED_FIRST_CALL and
                int(fields.get("lr", "0"), 0) == EXPECTED_FIRST_RETURN and
                int(fields.get("r3", "1"), 0) == 0 and
                int(fields.get("instructions", "0")) > 0 and
                int(fields.get("instructions", "4096")) < 4096 and
                fields.get("function_dispatches") == "1" and
                fields.get("containment_normal") == "1" and
                fields.get("containment_signal") == "1" and
                fields.get("containment_timeout") == "1",
                "guarded child did not stop at the exact typed boundary")

    recent = [f"0x{value}" for value in fields["recent"].split(",")
              if value]
    require(recent and int(recent[-1], 0) == EXPECTED_FIRST_CALL,
            "bounded recent-PC trace lacks the first import call")
    local_files = [
        root / "include/static_runtime/apf_first_entry_gate.h",
        root / "include/static_runtime/apf_first_entry_xenon_bridge.h",
        root / "include/static_runtime/apf_guest_instruction_budget.h",
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "src/static_runtime/apf_first_entry_xenon_bridge.cpp",
        root / "src/static_runtime/apf_guest_instruction_budget.cpp",
        root / "tools/apf_guarded_first_entry_execute.py",
    ]
    report = {
        "schema": SCHEMA,
        "result": {
            "former_composed_corpus_blocker_revalidated": True,
            "former_instruction_budget_blocker_revalidated": True,
            "entry_call_authorized_in_isolated_child": True,
            "entry_called_in_isolated_child": True,
            "translated_title_code_executed": True,
            "expected_first_typed_boundary_reached": True,
            "continued_past_first_typed_boundary": False,
            "child_outcome": fields["outcome"],
            "signal_number": 0,
            "native_boot_proved": False,
            "main_menu_proved": False,
        },
        "authorization_gates": {
            "retail_xex_sha256_exact": True,
            "retail_volume_sha256_exact": True,
            "decoded_image_sha256_and_size_exact": True,
            "composed_report_and_complete_tree_exact": True,
            "instrumentation_report_and_complete_tree_exact": True,
            "all_instruction_hooks_recounted": hook_count,
            "v1_readiness_report_and_pinned_files_exact": True,
            "imported_data_runtime_prerequisites_revalidated_in_child": True,
            "dispatch_mapping_count_revalidated": mapping_count,
            "typed_bridge_binding_count_revalidated": len(typed_imports),
            "child_containment_normal_revalidated": True,
            "child_containment_signal_revalidated": True,
            "child_containment_timeout_revalidated": True,
            "instruction_limit": 4096,
            "function_dispatch_limit": 64,
        },
        "generated_execution": {
            "entry": f"0x{EXPECTED_ENTRY:08X}",
            "first_import_call": f"0x{EXPECTED_FIRST_CALL:08X}",
            "first_import_return": f"0x{EXPECTED_FIRST_RETURN:08X}",
            "first_import_thunk": f"0x{EXPECTED_FIRST_THUNK:08X}",
            "first_import": "RtlImageXexHeaderField",
            "adapter_return_value_r3": "0x00000000",
            "executed_guest_instruction_count": int(fields["instructions"]),
            "function_dispatch_count": int(fields["function_dispatches"]),
            "last_executed_guest_pc": fields["last_pc"],
            "recent_executed_guest_pcs": recent,
            "terminal_semantics": (
                "typed adapter completed the absent DEFAULT_HEAP_SIZE query; "
                "the bridge then threw before generated continuation"
            ),
        },
        "outcome_classification": {
            "implemented": [
                "expected_typed_boundary", "budget_exhaustion",
                "import_abort", "signal", "timeout", "unexpected_return",
                "prerequisite_failure", "unexpected_exception",
            ],
            "observed": "expected_typed_boundary",
        },
        "inputs": {
            "retail_xex": pin(xex, root),
            "retail_volume": pin(volume, root),
            "decoded_image": {
                "size": decoded.stat().st_size,
                "sha256": sha256_file(decoded),
                "temporary_validator_artifact": True,
            },
            "composed_report": pin(composed_report_path, root),
            "budget_report": pin(budget_report_path, root),
            "v1_readiness_report": pin(readiness_report_path, root),
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
            "temporary_generated_objects_deleted": True,
            "guest_execution_process": "forked bounded child",
            "timeout_milliseconds": 5000,
            "retail_inputs_modified": False,
        },
        "portme": [
            "// PORTME: implement the next import/indirect/runtime boundary "
            "before allowing generated code to continue beyond 0x84BF1888.",
            "// PORTME: replace 304 nonfrontier import abort definitions with "
            "exact guest-ABI semantics as their paths become reachable.",
            "// PORTME: recover 1,076 remaining switch-tail occurrences and "
            "complete VSCR.SAT, frsqrte/FPSCR, and cache/device coherency.",
            "// PORTME: the function-dispatch ledger currently accounts the "
            "typed import dispatch; per-instruction coverage remains the "
            "hard dynamic execution bound for direct generated calls.",
        ],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(result_line + "\n", encoding="utf-8")
    print(result_line)
    print(
        "APF_GUARDED_FIRST_ENTRY_EXECUTION_PASS "
        f"instructions={fields['instructions']} function_dispatches=1 "
        f"last_pc=0x{EXPECTED_FIRST_CALL:08X} lr=0x{EXPECTED_FIRST_RETURN:08X} "
        "outcome=expected_typed_boundary continued=0 native_boot=0 "
        "temporary_outputs_deleted=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
