#!/usr/bin/env python3
"""Build deterministic evidence for the isolated APF boot leaf adapters."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess


ROOT = Path(__file__).resolve().parents[1]
XENIA = Path("/media/noah/Storage/.codex-tmp/xenia-source")
FRONTIER_PATH = ROOT / "reports/static_recomp/apf2k8_static_boot_import_frontier.json"
INDIRECT_FRONTIER_PATH = (
    ROOT / "reports/static_recomp/apf2k8_boot_indirect_frontier.json"
)
FRONTIER_TOOL_PATH = ROOT / "tools/apf_static_boot_import_frontier.py"
XEX_REPORT_PATH = ROOT / "reports/headers/apf2k8_xex_report.json"
XEX_HEADER_PATH = ROOT / "reports/headers/apf2k8_xex_header.bin"
DISPATCH_BOUNDARY_PATH = (
    ROOT / "reports/static_recomp/apf2k8_xex_dispatch_boundary.json"
)
IMPORTED_DATA_FRONTIER_PATH = (
    ROOT / "reports/static_recomp/apf2k8_imported_data_frontier.json"
)
GENERATED = ROOT / "build-static-recomp-apf/ppc-filtered"

IMPLEMENTED = {
    "DbgPrint": {
        "arguments": ["r3=exact retail format", "r4=signed decimal value"],
        "result": "r3 = X_STATUS_SUCCESS; structured event recorded",
    },
    "ExGetXConfigSetting": {
        "arguments": [
            "r3=category", "r4=setting", "r5=buffer",
            "r6=buffer_size", "r7=required_size",
        ],
        "result": "r3 = X_STATUS_SUCCESS for the two exact variants",
    },
    "KeGetCurrentProcessType": {"arguments": [], "result": "r3 = process_type"},
    "KeTlsAlloc": {"arguments": [], "result": "r3 = TLS index or 0xFFFFFFFF"},
    "KeTlsFree": {"arguments": ["r3=tls_index"], "result": "r3 = BOOL"},
    "KeTlsGetValue": {"arguments": ["r3=tls_index"], "result": "r3 = TLS value"},
    "KeTlsSetValue": {
        "arguments": ["r3=tls_index", "r4=tls_value"],
        "result": "r3 = BOOL",
    },
    "NtAllocateVirtualMemory": {
        "arguments": [
            "r3=BE PVOID*", "r4=BE SIZE_T*", "r5=exact allocation flags",
            "r6=X_PAGE_READWRITE", "r7=FALSE debug memory",
        ],
        "result": "r3 = NTSTATUS; successful BE base/rounded-size writes",
    },
    "NtClose": {
        "arguments": ["r3=adapter-owned event handle"],
        "result": "r3 = NTSTATUS; release one handle reference",
    },
    "NtCreateEvent": {
        "arguments": [
            "r3=BE HANDLE*", "r4=optional exact X_OBJECT_ATTRIBUTES",
            "r5=event type", "r6=initial state",
        ],
        "result": "r3 = NTSTATUS; successful BE event-handle write",
    },
    "NtFreeVirtualMemory": {
        "arguments": [
            "r3=BE PVOID*", "r4=BE SIZE_T*", "r5=exact free type",
            "r6=FALSE debug memory",
        ],
        "result": "r3 = NTSTATUS; successful BE base/size writes",
    },
    "NtQueryVirtualMemory": {
        "arguments": ["r3=base address", "r4=BE 28-byte information", "r5=0"],
        "result": "r3 = NTSTATUS; seven BE u32 information fields",
    },
    "NtWaitForSingleObjectEx": {
        "arguments": [
            "r3=adapter-owned event handle", "r4=wait mode 1",
            "r5=alertable BOOL", "r6=optional BE s64 relative timeout",
        ],
        "result": (
            "r3 = NTSTATUS for success/zero-timeout/invalid handle; "
            "scheduler_blocked for a pending wait"
        ),
    },
    "RtlCompareMemoryUlong": {
        "arguments": ["r3=source", "r4=length_bytes", "r5=pattern"],
        "result": "r3 = matching leading bytes",
    },
    "RtlEnterCriticalSection": {
        "arguments": ["r3=critical_section"],
        "result": "void; scheduler_blocked stops on contention",
    },
    "RtlInitializeCriticalSection": {
        "arguments": ["r3=critical_section"],
        "result": "void",
    },
    "RtlInitAnsiString": {
        "arguments": ["r3=destination X_ANSI_STRING", "r4=source PCSZ"],
        "result": "void; r3 is preserved",
    },
    "RtlNtStatusToDosError": {
        "arguments": ["r3=proved negative NTSTATUS"],
        "result": (
            "r3 = sign-extended Win32 error for the two proved statuses; "
            "every other status stops as unsupported_variant"
        ),
    },
    "RtlImageXexHeaderField": {
        "arguments": ["r3=retail XEX2 header", "r4=0x00020401"],
        "result": "r3 = NULL because DEFAULT_HEAP_SIZE is absent",
    },
    "RtlLeaveCriticalSection": {
        "arguments": ["r3=critical_section"],
        "result": "void; ownership and waiter states fail closed",
    },
    "XGetAVPack": {"arguments": [], "result": "r3 = configured AV pack"},
    "XGetLanguage": {"arguments": [], "result": "r3 = configured language"},
    "XamShowMessageBoxUIEx": {
        "arguments": [
            "r3=255", "r4=NULL title", "r5=APF UTF-16 message",
            "r6=one button", "r7=one-pointer button array",
            "r8=active button 0", "r9=flags 1",
            "r10=opaque exact value 1", "stack arg9=opaque result object",
            "stack arg10=XAM_OVERLAPPED",
        ],
        "result": (
            "ui_requested boundary; explicit host completion resumes with "
            "r3=X_ERROR_IO_PENDING and completed overlapped/event state"
        ),
    },
    "XexCheckExecutablePrivilege": {
        "arguments": ["r3=system_flag_bit_index"],
        "result": "r3 = BOOL",
    },
}

TERMINAL = {
    "HalReturnToFirmware": {
        "arguments": ["r3=firmware_reentry"],
        "outcome": "firmware_return",
    },
    "KeBugCheckEx": {
        "arguments": ["r3=code", "r4=param1", "r5=param2", "r6=param3", "r7=param4"],
        "outcome": "bugcheck",
    },
    "KeBugCheck": {
        "arguments": ["r3=code"],
        "outcome": "bugcheck",
    },
    "XamLoaderTerminateTitle": {
        "arguments": [],
        "outcome": "title_terminate",
    },
}

EXCEPTION_REQUIRED = {
    "RtlRaiseException": {
        "arguments": ["r3=exception_record"],
        "dispatch_status": "exception_required",
        "reason": "continuable exception requires guest SEH dispatch/unwind",
    },
}

THREAD_CREATE_REQUIRED = {
    "ExCreateThread": {
        "dispatch_status": "thread_create_requested",
        "reason": (
            "scheduler does not yet own the guest handle/object, guarded "
            "stack, TLS/PCR/CPU context, runnable/exit state, or teardown"
        ),
        "resumable_without_scheduler_lifecycle": False,
    },
}

EXPECTED_DIRECT_SITES = {
    "DbgPrint": [0x84BE9EB4],
    "ExCreateThread": [0x84BF108C],
    "ExGetXConfigSetting": [0x84BE9B84, 0x84BE9BB4],
    "HalReturnToFirmware": [0x84BF1994],
    "KeBugCheck": [0x84BDAA24],
    "KeBugCheckEx": [0x84BECD1C, 0x84BEDA9C, 0x84BEED5C, 0x84BEF30C],
    "KeGetCurrentProcessType": [
        0x84BECCF8, 0x84BED908, 0x84BEDA78, 0x84BEED38, 0x84BEF2E8,
    ],
    "KeTlsAlloc": [0x84BDE6F8, 0x84BDEAE4],
    "KeTlsFree": [0x84BDE800],
    "KeTlsGetValue": [0x84BDE770, 0x84BDE868],
    "KeTlsSetValue": [0x84BDE788, 0x84BDEAFC],
    "NtAllocateVirtualMemory": [
        0x84BEBACC, 0x84BEBB1C, 0x84BEBB50, 0x84BEBE0C, 0x84BECE14,
        0x84BED00C, 0x84BED050, 0x84BED0A0, 0x84BED7B8, 0x84BED808,
        0x84BEE1CC,
    ],
    "NtClose": [0x84BE9A8C],
    "NtCreateEvent": [0x84BE7088, 0x84BE9A2C],
    "NtFreeVirtualMemory": [
        0x84BEBB70, 0x84BED10C, 0x84BED244, 0x84BED830, 0x84BEEF3C,
        0x84BEF50C,
    ],
    "NtQueryVirtualMemory": [0x84BED6F8, 0x84BED750],
    "NtWaitForSingleObjectEx": [0x84BF0E3C],
    "RtlCompareMemoryUlong": [
        0x84BEC138, 0x84BEC1E4, 0x84BEC324, 0x84BEC3F0, 0x84BEC900,
        0x84BECB74, 0x84BEF73C,
    ],
    "RtlEnterCriticalSection": [
        0x84B579CC, 0x84BDE26C, 0x84BEDADC, 0x84BEED8C, 0x84BEF3A0,
        0x84BF0C6C, 0x84BF0CF0,
    ],
    "RtlImageXexHeaderField": [0x84BF1888],
    "RtlInitAnsiString": [0x84BF0BAC, 0x84BF0DD4],
    "RtlInitializeCriticalSection": [
        0x84B5796C, 0x84BDE614, 0x84BED954, 0x84D05740, 0x84D05778,
        0x84D057B0,
    ],
    "RtlLeaveCriticalSection": [
        0x84B57A0C, 0x84BDE0C0, 0x84BDE20C, 0x84BEE164, 0x84BEE2F4,
        0x84BEEF18, 0x84BEEFB4, 0x84BEFB04, 0x84BF0CA4, 0x84BF0D30,
    ],
    "RtlNtStatusToDosError": [0x84BF0D64],
    "RtlRaiseException": [0x84BEE284, 0x84BEFA84],
    "XGetAVPack": [0x84BE9B4C],
    "XGetLanguage": [0x84BE9BD4],
    "XamLoaderTerminateTitle": [0x84BE9D50, 0x84BE9EC4],
    "XamShowMessageBoxUIEx": [0x84BE9A68],
    "XexCheckExecutablePrivilege": [0x84BE9B40],
}

EXPECTED_TAIL_DIRECT_SITES = {
    ("sub_84BDAA20", "KeBugCheck"): 0x84BDAA24,
    ("sub_84BDE6F8", "KeTlsAlloc"): 0x84BDE6F8,
    ("sub_84BDE0B0", "RtlLeaveCriticalSection"): 0x84BDE0C0,
}

EXPECTED_PROVED_INDIRECT_IMPORT_SITES = [
    (0x84BDE7E4, "sub_84BDE7B0", "KeTlsFree"),
    (0x84BDE878, "sub_84BDE840", "KeTlsGetValue"),
    (0x84BDE8AC, "sub_84BDE840", "KeTlsSetValue"),
    (0x84BDEB60, "sub_84BDEA98", "KeTlsSetValue"),
]

VM_ALLOCATE_SITE_SHAPES = {
    0x84BEBACC: ("commit", ["0x60001000"]),
    0x84BEBB1C: ("reserve", ["0x60002000"]),
    0x84BEBB50: ("commit", ["0x60001000"]),
    0x84BEBE0C: ("commit", ["0x60001000"]),
    0x84BECE14: ("commit", ["0x60001000"]),
    0x84BED00C: ("reserve", ["0x60002000"]),
    0x84BED050: ("reserve", ["0x60002000"]),
    0x84BED0A0: ("commit", ["0x60001000"]),
    0x84BED7B8: ("reserve", ["0x60002000"]),
    0x84BED808: ("commit", ["0x60001000"]),
    0x84BEE1CC: ("commit", ["0x60001000", "0x60801000"]),
}

VM_FREE_SITE_SHAPES = {
    0x84BEBB70: "release",
    0x84BED10C: "release",
    0x84BED244: "decommit",
    0x84BED830: "release",
    0x84BEEF3C: "release",
    0x84BEF50C: "release",
}

VM_QUERY_SITE_SHAPES = {
    0x84BED6F8: "X_MEMORY_BASIC_INFORMATION at r4, r5=0",
    0x84BED750: "X_MEMORY_BASIC_INFORMATION at r4, r5=0",
}

UNSUPPORTED: dict[str, str] = {}

XENIA_REFERENCES = [
    "src/xenia/memory.cc",
    "src/xenia/memory.h",
    "src/xenia/kernel/kernel_state.cc",
    "src/xenia/kernel/kernel_state.h",
    "src/xenia/kernel/user_module.cc",
    "src/xenia/kernel/user_module.h",
    "src/xenia/kernel/util/shim_utils.h",
    "src/xenia/kernel/util/xex2_info.h",
    "src/xenia/kernel/xthread.cc",
    "src/xenia/kernel/xthread.h",
    "src/xenia/kernel/xevent.cc",
    "src/xenia/kernel/xevent.h",
    "src/xenia/kernel/xobject.h",
    "src/xenia/kernel/util/object_table.cc",
    "src/xenia/kernel/util/object_table.h",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_ob.cc",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_debug.cc",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_error.cc",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_hal.cc",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_threading.cc",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_rtl.cc",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_strings.cc",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_xconfig.cc",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_modules.cc",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_memory.cc",
    "src/xenia/kernel/xboxkrnl/xboxkrnl_table.inc",
    "src/xenia/kernel/xam/xam_info.cc",
    "src/xenia/kernel/xam/xam_table.inc",
    "src/xenia/kernel/xam/xam_ui.cc",
    "src/xenia/xbox.h",
    "LICENSE",
]

LOCAL_INPUTS = [
    "include/static_runtime/apf_boot_leaf_adapters.h",
    "src/static_runtime/apf_boot_leaf_adapters.c",
    "tests/apf_boot_leaf_adapters_test.c",
    "reports/static_recomp/apf2k8_static_boot_import_frontier.json",
    "reports/static_recomp/apf2k8_boot_indirect_frontier.json",
    "tools/apf_static_boot_import_frontier.py",
    "reports/headers/apf2k8_xex_report.json",
    "reports/headers/apf2k8_xex_header.bin",
    "reports/static_recomp/apf2k8_xex_dispatch_boundary.json",
    "reports/static_recomp/apf2k8_imported_data_frontier.json",
    "tools/xex_extract_pe.cpp",
    "tools/vendor/Cxbx-Reloaded/src/core/kernel/exports/EmuKrnlRtl.cpp",
    "tools/vendor/Cxbx-Reloaded/src/core/kernel/exports/EmuKrnlKe.cpp",
    "tools/vendor/Cxbx-Reloaded/src/core/kernel/common/types.h",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, display_path: str) -> dict[str, object]:
    return {
        "path": display_path,
        "sha256": sha256(path),
        "size": path.stat().st_size,
    }


def git_head(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_frontier_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "apf_static_boot_import_frontier_for_leaf_adapters",
        FRONTIER_TOOL_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_function_body(
    caller: str, source_texts: dict[Path, str]
) -> tuple[Path, str, int, str]:
    needle = f"PPC_FUNC_IMPL(__imp__{caller}) {{"
    hits: list[tuple[Path, int]] = []
    for path, text in source_texts.items():
        start = text.find(needle)
        if start >= 0:
            assert text.find(needle, start + 1) < 0
            hits.append((path, start))
    assert len(hits) == 1, (caller, hits)
    path, start = hits[0]
    text = source_texts[path]
    end = text.find("\n__attribute__((alias(", start)
    if end < 0:
        end = len(text)
    line = text.count("\n", 0, start) + 1
    return path, text, start, text[start:end]


def extract_calls(
    caller: str,
    import_name: str,
    source_texts: dict[Path, str],
) -> list[dict[str, object]]:
    path, full_text, body_start, body = find_function_body(caller, source_texts)
    pattern = re.compile(
        rf"ctx\.lr = (0x[0-9A-Fa-f]+);\s*\n\s*__imp__{re.escape(import_name)}"
        rf"\(ctx, base\);"
    )
    calls: list[dict[str, object]] = []
    for match in pattern.finditer(body):
        return_address = int(match.group(1), 16)
        call_marker = match.group(0).rfind(f"__imp__{import_name}")
        absolute_call_offset = body_start + match.start() + call_marker
        after_call = body[match.end() :].lstrip().splitlines()
        calls.append(
            {
                "call_address": f"0x{return_address - 4:08X}",
                "call_kind": "linking_branch",
                "caller": caller,
                "dispatch_path": "direct_generated_call",
                "generated_line": full_text.count("\n", 0, absolute_call_offset)
                + 1,
                "generated_source": str(path.relative_to(ROOT)),
                "next_generated_line_is_label": bool(after_call)
                and after_call[0].startswith("loc_"),
                "return_address": f"0x{return_address:08X}",
            }
        )

    tail_pattern = re.compile(
        rf"// b 0x[0-9A-Fa-f]+\s*\n\s*"
        rf"__imp__{re.escape(import_name)}\(ctx, base\);\s*\n\s*return;"
    )
    tail_matches = list(tail_pattern.finditer(body))
    tail_key = (caller, import_name)
    if tail_key in EXPECTED_TAIL_DIRECT_SITES:
        assert len(tail_matches) == 1, tail_key
        match = tail_matches[0]
        call_marker = match.group(0).find(f"__imp__{import_name}")
        absolute_call_offset = body_start + match.start() + call_marker
        call_address = EXPECTED_TAIL_DIRECT_SITES[tail_key]
        calls.append(
            {
                "call_address": f"0x{call_address:08X}",
                "call_kind": "tail_branch",
                "caller": caller,
                "dispatch_path": "direct_generated_call",
                "generated_line": full_text.count(
                    "\n", 0, absolute_call_offset
                ) + 1,
                "generated_source": str(path.relative_to(ROOT)),
                "inherited_lr": True,
                "next_generated_line_is_label": False,
                "return_address": None,
            }
        )
    else:
        assert not tail_matches, tail_key
    return calls


def call_prefix(
    caller: str,
    import_name: str,
    return_address: int,
    source_texts: dict[Path, str],
) -> str:
    _, _, _, body = find_function_body(caller, source_texts)
    needle = (
        f"ctx.lr = 0x{return_address:08X};\n"
        f"\t__imp__{import_name}(ctx, base);"
    )
    start = body.find(needle)
    assert start >= 0, (caller, import_name, hex(return_address))
    assert body.find(needle, start + 1) < 0
    return body[max(0, start - 1200):start]


def load_relevant_generated_sources(callers: set[str]) -> dict[Path, str]:
    selected: dict[Path, str] = {}
    found: set[str] = set()
    for path in sorted(GENERATED.glob("ppc_recomp.*.cpp")):
        text = path.read_text(encoding="utf-8")
        matched = False
        for caller in sorted(callers):
            needle = f"PPC_FUNC_IMPL(__imp__{caller}) {{"
            if needle in text:
                found.add(caller)
                matched = True
        if matched:
            selected[path] = text
    # Verify every requested implementation symbol was uniquely located.
    found = {
        caller
        for caller in callers
        if any(f"PPC_FUNC_IMPL(__imp__{caller}) {{" in text
               for text in selected.values())
    }
    assert found == callers, sorted(callers - found)
    return selected


def build_report() -> dict[str, object]:
    frontier = json.loads(FRONTIER_PATH.read_text(encoding="utf-8"))
    indirect_frontier = json.loads(
        INDIRECT_FRONTIER_PATH.read_text(encoding="utf-8")
    )
    xex_report = json.loads(XEX_REPORT_PATH.read_text(encoding="utf-8"))
    dispatch_boundary = json.loads(
        DISPATCH_BOUNDARY_PATH.read_text(encoding="utf-8")
    )
    imported_data_frontier = json.loads(
        IMPORTED_DATA_FRONTIER_PATH.read_text(encoding="utf-8")
    )
    xex_header_bytes = XEX_HEADER_PATH.read_bytes()
    assert frontier["schema"] == "apf2k8_static_boot_import_frontier/v1"
    assert frontier["result"]["boundary_stopped_total_nodes"] == 103
    assert indirect_frontier["schema"] == "apf2k8_boot_indirect_frontier/v1"
    assert indirect_frontier["result"]["augmented_total_nodes"] == 458
    assert indirect_frontier["result"]["augmented_callable_imports"] == 30
    assert indirect_frontier["result"]["translated_title_code_executed"] is False
    assert dispatch_boundary["schema"] == "apf2k8_xex_dispatch_boundary/v1"
    assert imported_data_frontier["schema"] == (
        "apf2k8_imported_data_frontier/v1"
    )
    assert imported_data_frontier["result"]["augmented_frontier_nodes"] == 458
    assert imported_data_frontier["result"][
        "slots_seeded_by_isolated_bootstrap"] == 2
    assert imported_data_frontier["result"][
        "all_thirteen_imported_data_slots_resolved"] is False
    assert imported_data_frontier["result"][
        "translated_title_code_executed"] is False
    assert dispatch_boundary["xex_security_and_pages"]["load_address"] == (
        "0x82000000"
    )
    assert dispatch_boundary["xex_security_and_pages"][
        "security_image_end_exclusive"] == "0x85380000"
    assert dispatch_boundary["dispatch"]["dispatch_start"] == "0x85380000"
    assert dispatch_boundary["dispatch"][
        "dispatch_host_page_rounded_end_exclusive"] == "0x86133000"
    xex_prefix = struct.unpack_from(">6I", xex_header_bytes, 0)
    assert xex_prefix == (
        0x58455832, 0x00000001, 0x00007000,
        0x00000000, 0x00000090, 15,
    )
    retail_options = [
        struct.unpack_from(">2I", xex_header_bytes, 24 + index * 8)
        for index in range(xex_prefix[5])
    ]
    reported_options = [
        (int(row["key"], 16), int(row["value_or_offset"], 16))
        for row in xex_report["xex_header"]["optional_headers"]
    ]
    assert retail_options == reported_options
    assert len(retail_options) == 15
    assert all(key != 0x00020401 for key, _ in retail_options)
    frontier_module = load_frontier_module()
    numbered = [
        GENERATED / f"ppc_recomp.{index}.cpp"
        for index in range(frontier_module.EXPECTED_NUMBERED_SOURCE_COUNT)
    ]
    generated_calls, _, _, _ = frontier_module.parse_generated(numbered)
    callable_items = [
        item for item in xex_report["imports"]["items"]
        if item["thunk_address"] is not None
    ]
    callable_thunk_addresses = [
        int(str(item["thunk_address"]), 16) for item in callable_items
    ]
    assert (min(callable_thunk_addresses), max(callable_thunk_addresses) + 4) == (
        0x84D07B6C, 0x84D09040,
    )
    callable_by_symbol = {
        "__imp__" + item["name"]: item for item in callable_items
    }
    callable_symbols = set(callable_by_symbol)
    proved_edges_by_caller: dict[str, set[str]] = defaultdict(set)
    for site in indirect_frontier["original_indirect_sites"]:
        for target in site["proved_targets"]:
            proved_edges_by_caller[site["caller"]].add(target["symbol"])

    reached_generated: set[str] = set()
    reached_imports: set[str] = set()
    pending: deque[str] = deque([frontier_module.ENTRY])
    while pending:
        caller = pending.popleft()
        if caller in reached_generated:
            continue
        assert caller in generated_calls
        reached_generated.add(caller)
        if caller in frontier_module.BOUNDARIES:
            continue
        for callee in sorted(
            set(generated_calls[caller]) |
            proved_edges_by_caller.get(caller, set())
        ):
            if callee in generated_calls:
                if callee not in reached_generated:
                    pending.append(callee)
            else:
                assert callee in callable_symbols, (caller, callee)
                reached_imports.add(callee)

    active = reached_generated - frontier_module.BOUNDARIES
    assert (len(reached_generated), len(active), len(reached_imports)) == (
        428, 426, 30
    )
    direct_callers: dict[str, set[str]] = defaultdict(set)
    direct_site_count = 0
    for caller in active:
        for callee in generated_calls[caller]:
            if callee in callable_symbols:
                direct_callers[callee].add(caller)
                direct_site_count += 1
    assert direct_site_count == 87

    rows: dict[str, dict[str, object]] = {}
    for symbol in reached_imports:
        item = callable_by_symbol[symbol]
        rows[str(item["name"])] = {
            **item,
            "callers": sorted(direct_callers[symbol]),
        }
    assert set(rows) == set(EXPECTED_DIRECT_SITES)

    proved_indirect_by_name: dict[str, list[dict[str, object]]] = defaultdict(list)
    proved_indirect_tuples: list[tuple[int, str, str]] = []
    for site in indirect_frontier["original_indirect_sites"]:
        for target in site["proved_targets"]:
            symbol = target["symbol"]
            if symbol not in callable_symbols:
                continue
            name = str(callable_by_symbol[symbol]["name"])
            address = int(site["call_instruction_address"], 16)
            proved_indirect_tuples.append((address, site["caller"], name))
            proved_indirect_by_name[name].append(
                {
                    "call_address": site["call_instruction_address"],
                    "call_kind": "indirect_bctrl",
                    "caller": site["caller"],
                    "dispatch_path": "proved_indirect_frontier",
                    "generated_source": (
                        "build-static-recomp-apf/ppc-filtered/" +
                        site["generated_source"]
                    ),
                    "return_address": site["return_address"],
                    "target_thunk_address": target["address"],
                }
            )
    assert sorted(proved_indirect_tuples) == sorted(
        EXPECTED_PROVED_INDIRECT_IMPORT_SITES
    )

    classified_sets = [
        set(IMPLEMENTED), set(TERMINAL), set(EXCEPTION_REQUIRED),
        set(THREAD_CREATE_REQUIRED), set(UNSUPPORTED),
    ]
    assert set().union(*classified_sets) == set(rows)
    assert set(IMPLEMENTED).isdisjoint(TERMINAL)
    assert set(IMPLEMENTED).isdisjoint(EXCEPTION_REQUIRED)
    assert set(IMPLEMENTED).isdisjoint(UNSUPPORTED)
    assert set(IMPLEMENTED).isdisjoint(THREAD_CREATE_REQUIRED)
    assert set(TERMINAL).isdisjoint(EXCEPTION_REQUIRED)
    assert set(TERMINAL).isdisjoint(THREAD_CREATE_REQUIRED)
    assert set(TERMINAL).isdisjoint(UNSUPPORTED)
    assert set(EXCEPTION_REQUIRED).isdisjoint(THREAD_CREATE_REQUIRED)
    assert set(EXCEPTION_REQUIRED).isdisjoint(UNSUPPORTED)
    assert set(THREAD_CREATE_REQUIRED).isdisjoint(UNSUPPORTED)

    relevant_callers = {
        caller for row in rows.values() for caller in row["callers"]
    }
    relevant_callers.update({
        "sub_84679E00", "sub_84B578D8", "sub_84BE84A0", "sub_84BF7340",
    })
    source_texts = load_relevant_generated_sources(relevant_callers)

    def direct_calls_for(name: str) -> list[dict[str, object]]:
        calls = [
            call
            for caller in rows[name]["callers"]
            for call in extract_calls(caller, name, source_texts)
        ]
        calls.sort(key=lambda call: (call["call_address"], call["caller"]))
        assert [int(call["call_address"], 16) for call in calls] == (
            EXPECTED_DIRECT_SITES[name]
        )
        return calls

    implemented_rows: list[dict[str, object]] = []
    for name in sorted(IMPLEMENTED):
        frontier_row = rows[name]
        calls = direct_calls_for(name)
        indirect_calls = sorted(
            proved_indirect_by_name.get(name, []),
            key=lambda call: call["call_address"],
        )
        implemented_rows.append(
            {
                "abi": IMPLEMENTED[name],
                "calls": calls,
                "direct_static_call_sites": len(calls),
                "library": frontier_row["library"],
                "name": name,
                "ordinal": frontier_row["ordinal"],
                "proved_indirect_dispatches": indirect_calls,
                "proved_indirect_static_sites": len(indirect_calls),
                "reference_address": frontier_row["reference_address"],
                "static_call_sites": len(calls),
                "thunk_address": frontier_row["thunk_address"],
            }
        )

    terminal_rows: list[dict[str, object]] = []
    for name in sorted(TERMINAL):
        frontier_row = rows[name]
        calls = direct_calls_for(name)
        terminal_rows.append(
            {
                "abi": TERMINAL[name],
                "calls": calls,
                "direct_static_call_sites": len(calls),
                "library": frontier_row["library"],
                "name": name,
                "ordinal": frontier_row["ordinal"],
                "static_call_sites": len(calls),
                "thunk_address": frontier_row["thunk_address"],
                "resumable": False,
            }
        )

    exception_rows: list[dict[str, object]] = []
    for name in sorted(EXCEPTION_REQUIRED):
        frontier_row = rows[name]
        calls = direct_calls_for(name)
        exception_rows.append(
            {
                "abi": EXCEPTION_REQUIRED[name],
                "calls": calls,
                "direct_static_call_sites": len(calls),
                "library": frontier_row["library"],
                "name": name,
                "ordinal": frontier_row["ordinal"],
                "static_call_sites": len(calls),
                "thunk_address": frontier_row["thunk_address"],
                "resumable_without_seh": False,
            }
        )

    thread_create_rows: list[dict[str, object]] = []
    for name in sorted(THREAD_CREATE_REQUIRED):
        frontier_row = rows[name]
        calls = direct_calls_for(name)
        thread_create_rows.append(
            {
                "abi": THREAD_CREATE_REQUIRED[name],
                "calls": calls,
                "direct_static_call_sites": len(calls),
                "library": frontier_row["library"],
                "name": name,
                "ordinal": frontier_row["ordinal"],
                "static_call_sites": len(calls),
                "thunk_address": frontier_row["thunk_address"],
                "resumable_without_scheduler_lifecycle": False,
            }
        )

    unsupported_rows: list[dict[str, object]] = []
    for name in sorted(UNSUPPORTED):
        row = rows[name]
        calls = direct_calls_for(name)
        unsupported_rows.append(
            {
                "calls": calls,
                "callers": row["callers"],
                "direct_static_call_sites": len(calls),
                "library": row["library"],
                "name": name,
                "ordinal": row["ordinal"],
                "portme": (
                    f"// PORTME at {row['thunk_address']}: {UNSUPPORTED[name]}."
                ),
                "static_call_sites": len(calls),
                "thunk_address": row["thunk_address"],
            }
        )

    generated_inputs = [
        file_record(path, str(path.relative_to(ROOT)))
        for path in sorted(source_texts)
    ]
    xenia_inputs = [
        file_record(XENIA / path, path) for path in XENIA_REFERENCES
    ]
    local_inputs = [file_record(ROOT / path, path) for path in LOCAL_INPUTS]

    rtl_row = next(
        row for row in implemented_rows if row["name"] == "RtlCompareMemoryUlong"
    )
    assert all(call["next_generated_line_is_label"] for call in rtl_row["calls"])

    privilege_row = next(
        row
        for row in implemented_rows
        if row["name"] == "XexCheckExecutablePrivilege"
    )
    assert len(privilege_row["calls"]) == 1
    privilege_call = privilege_row["calls"][0]
    assert privilege_call["call_address"] == "0x84BE9B40"
    assert privilege_call["caller"] == "sub_84BE9B20"
    assert privilege_call["call_kind"] == "linking_branch"
    assert privilege_call["return_address"] == "0x84BE9B44"

    _, _, _, xconfig_body = find_function_body("sub_84BE9B20", source_texts)
    xconfig_patterns = [
        (
            r"ctx\.r7\.s64 = ctx\.r1\.s64 \+ 80;.*?"
            r"ctx\.r6\.s64 = 4;.*?ctx\.r5\.s64 = ctx\.r1\.s64 \+ 84;.*?"
            r"ctx\.r4\.s64 = 2;.*?ctx\.r3\.s64 = 2;.*?"
            r"ctx\.lr = 0x84BE9B88;\s*__imp__ExGetXConfigSetting"
        ),
        (
            r"ctx\.r7\.s64 = ctx\.r1\.s64 \+ 80;.*?"
            r"ctx\.r6\.s64 = 4;.*?ctx\.r5\.s64 = ctx\.r1\.s64 \+ 88;.*?"
            r"ctx\.r4\.s64 = 10;.*?ctx\.r3\.s64 = 3;.*?"
            r"ctx\.lr = 0x84BE9BB8;\s*__imp__ExGetXConfigSetting"
        ),
    ]
    assert all(re.search(pattern, xconfig_body, re.DOTALL)
               for pattern in xconfig_patterns)

    _, _, _, ansi_stack_body = find_function_body(
        "sub_84BF0B88", source_texts
    )
    assert re.search(
        r"ctx\.r4\.u64 = ctx\.r3\.u64;.*?"
        r"ctx\.r3\.s64 = ctx\.r1\.s64 \+ 80;.*?"
        r"ctx\.lr = 0x84BF0BB0;\s*__imp__RtlInitAnsiString",
        ansi_stack_body,
        re.DOTALL,
    )
    _, _, _, ansi_object_body = find_function_body(
        "sub_84BF0DB0", source_texts
    )
    assert re.search(
        r"ctx\.r30\.u64 = ctx\.r4\.u64;.*?"
        r"ctx\.r4\.u64 = ctx\.r5\.u64;.*?"
        r"ctx\.r3\.u64 = ctx\.r30\.u64;.*?"
        r"ctx\.lr = 0x84BF0DD8;\s*__imp__RtlInitAnsiString",
        ansi_object_body,
        re.DOTALL,
    )

    _, _, _, xstart_body = find_function_body("_xstart", source_texts)
    assert re.search(
        r"ctx\.r30\.u64 = ctx\.r3\.u64;.*?"
        r"ctx\.r11\.s64 = -2075328512;.*?"
        r"ctx\.r3\.s64 = ctx\.r11\.s64 \+ 14264;.*?"
        r"ctx\.r4\.u64 = ctx\.r30\.u64;.*?"
        r"ctx\.lr = 0x84BE9EB8;\s*__imp__DbgPrint",
        xstart_body,
        re.DOTALL,
    )
    assert ((-2075328512 + 14264) & 0xFFFFFFFF) == 0x844D37B8

    _, _, _, xex_field_body = find_function_body(
        "sub_84BF1850", source_texts
    )
    assert re.search(
        r"ctx\.r4\.s64 = 131072;.*?"
        r"ctx\.r3\.u64 = PPC_LOAD_U32\(ctx\.r11\.u32 \+ 88\);.*?"
        r"ctx\.r4\.u64 = ctx\.r4\.u64 \| 1025;.*?"
        r"ctx\.lr = 0x84BF188C;\s*"
        r"__imp__RtlImageXexHeaderField\(ctx, base\);.*?"
        r"ctx\.cr0\.compare<uint32_t>\(ctx\.r3\.u32, 0, ctx\.xer\);",
        xex_field_body,
        re.DOTALL,
    )

    implemented_by_name = {
        str(row["name"]): row for row in implemented_rows
    }
    vm_allocate_calls = implemented_by_name[
        "NtAllocateVirtualMemory"
    ]["calls"]
    vm_free_calls = implemented_by_name["NtFreeVirtualMemory"]["calls"]
    vm_query_calls = implemented_by_name[
        "NtQueryVirtualMemory"
    ]["calls"]
    assert {int(call["call_address"], 16) for call in vm_allocate_calls} == (
        set(VM_ALLOCATE_SITE_SHAPES)
    )
    assert {int(call["call_address"], 16) for call in vm_free_calls} == (
        set(VM_FREE_SITE_SHAPES)
    )
    assert {int(call["call_address"], 16) for call in vm_query_calls} == (
        set(VM_QUERY_SITE_SHAPES)
    )

    vm_allocate_shapes = []
    for call in vm_allocate_calls:
        call_address = int(call["call_address"], 16)
        operation, allocation_types = VM_ALLOCATE_SITE_SHAPES[call_address]
        prefix = call_prefix(
            str(call["caller"]), "NtAllocateVirtualMemory",
            int(str(call["return_address"]), 16), source_texts,
        )
        assert "ctx.r7.s64 = 0;" in prefix
        assert "ctx.r6.s64 = 4;" in prefix
        assert (
            f"ctx.r5.u64 = ctx.r5.u64 | "
            f"{8192 if operation == 'reserve' else 4096};"
        ) in prefix
        if call_address == 0x84BEE1CC:
            assert "ctx.r11.s64 = 8388608;" in prefix
            assert "ctx.r5.u64 = ctx.r11.u64 | 1610612736;" in prefix
            _, _, _, special_body = find_function_body(
                "sub_84BEDA38", source_texts
            )
            r24_assignments = re.findall(
                r"^\s*ctx\.r24\.[us][0-9]+\s*=.*$",
                special_body, re.MULTILINE,
            )
            assert [line.strip() for line in r24_assignments] == [
                "ctx.r24.s64 = 0;"
            ]
        else:
            assert "ctx.r5.s64 = 1610612736;" in prefix
        vm_allocate_shapes.append({
            "allocation_types": allocation_types,
            "call_address": call["call_address"],
            "caller": call["caller"],
            "debug_memory": 0,
            "operation": operation,
            "protect": "0x00000004 (X_PAGE_READWRITE)",
            "return_address": call["return_address"],
        })

    vm_free_shapes = []
    for call in vm_free_calls:
        call_address = int(call["call_address"], 16)
        operation = VM_FREE_SITE_SHAPES[call_address]
        prefix = call_prefix(
            str(call["caller"]), "NtFreeVirtualMemory",
            int(str(call["return_address"]), 16), source_texts,
        )
        assert "ctx.r6.s64 = 0;" in prefix
        if operation == "release":
            assert "ctx.r5.u64 = ctx.r5.u64 | 32768;" in prefix
        else:
            assert "ctx.r5.s64 = 16384;" in prefix
        vm_free_shapes.append({
            "call_address": call["call_address"],
            "caller": call["caller"],
            "debug_memory": 0,
            "free_type": (
                "0x00008000 (X_MEM_RELEASE)" if operation == "release"
                else "0x00004000 (X_MEM_DECOMMIT)"
            ),
            "operation": operation,
            "return_address": call["return_address"],
        })

    vm_query_shapes = []
    for call in vm_query_calls:
        call_address = int(call["call_address"], 16)
        prefix = call_prefix(
            str(call["caller"]), "NtQueryVirtualMemory",
            int(str(call["return_address"]), 16), source_texts,
        )
        assert "ctx.r5.s64 = 0;" in prefix
        vm_query_shapes.append({
            "call_address": call["call_address"],
            "caller": call["caller"],
            "information_size": 28,
            "r5": 0,
            "return_address": call["return_address"],
        })

    event_create_calls = implemented_by_name["NtCreateEvent"]["calls"]
    event_close_calls = implemented_by_name["NtClose"]["calls"]
    event_wait_calls = implemented_by_name[
        "NtWaitForSingleObjectEx"
    ]["calls"]
    assert [call["call_address"] for call in event_create_calls] == [
        "0x84BE7088", "0x84BE9A2C",
    ]
    assert [call["call_address"] for call in event_close_calls] == [
        "0x84BE9A8C",
    ]
    assert [call["call_address"] for call in event_wait_calls] == [
        "0x84BF0E3C",
    ]

    _, _, _, general_event_body = find_function_body(
        "sub_84BE7038", source_texts
    )
    assert re.search(
        r"ctx\.r6\.u64 = ctx\.r30\.u32 & 0xFF;.*?"
        r"ctx\.r5\.u64 = .*? & 0x1;.*?"
        r"ctx\.r3\.s64 = ctx\.r1\.s64 \+ 80;.*?"
        r"ctx\.lr = 0x84BE708C;\s*__imp__NtCreateEvent",
        general_event_body,
        re.DOTALL,
    )
    _, _, _, message_event_body = find_function_body(
        "sub_84BE99E0", source_texts
    )
    assert re.search(
        r"ctx\.r6\.s64 = 0;.*?ctx\.r5\.s64 = 1;.*?"
        r"ctx\.r4\.s64 = 0;.*?"
        r"ctx\.r3\.s64 = ctx\.r1\.s64 \+ 124;.*?"
        r"ctx\.lr = 0x84BE9A30;\s*__imp__NtCreateEvent",
        message_event_body,
        re.DOTALL,
    )
    assert re.search(
        r"ctx\.r3\.u64 = PPC_LOAD_U32\(ctx\.r1\.u32 \+ 124\);.*?"
        r"ctx\.lr = 0x84BE9A90;\s*__imp__NtClose",
        message_event_body,
        re.DOTALL,
    )

    message_box_row = implemented_by_name["XamShowMessageBoxUIEx"]
    assert len(message_box_row["calls"]) == 1
    message_box_call = message_box_row["calls"][0]
    assert message_box_call["call_address"] == "0x84BE9A68"
    assert message_box_call["call_kind"] == "linking_branch"
    assert message_box_call["caller"] == "sub_84BE99E0"
    assert message_box_call["return_address"] == "0x84BE9A6C"
    assert rows["XamShowMessageBoxUIEx"]["callers"] == ["sub_84BE99E0"]
    assert re.search(
        r"ctx\.r5\.s64 = 24;.*?ctx\.r4\.s64 = 0;.*?"
        r"ctx\.r3\.s64 = ctx\.r1\.s64 \+ 116;.*?"
        r"PPC_STORE_U32\(ctx\.r1\.u32 \+ 112, ctx\.r31\.u32\);.*?"
        r"ctx\.lr = 0x84BE9A10;\s*sub_84BD7E30.*?"
        r"ctx\.r11\.s64 = ctx\.r1\.s64 \+ 108;.*?"
        r"PPC_STORE_U32\(ctx\.r1\.u32 \+ 104, ctx\.r31\.u32\);.*?"
        r"PPC_STORE_U32\(ctx\.r11\.u32 \+ 0, ctx\.r31\.u32\);",
        message_event_body,
        re.DOTALL,
    )
    assert re.search(
        r"ctx\.r5\.s64 = ctx\.r1\.s64 \+ 104;.*?"
        r"ctx\.r11\.s64 = ctx\.r1\.s64 \+ 112;.*?"
        r"ctx\.r10\.u64 = ctx\.r29\.u64;.*?"
        r"ctx\.r9\.s64 = 1;.*?ctx\.r8\.s64 = 0;.*?"
        r"PPC_STORE_U32\(ctx\.r1\.u32 \+ 84, ctx\.r5\.u32\);.*?"
        r"ctx\.r7\.s64 = ctx\.r1\.s64 \+ 204;.*?"
        r"ctx\.r6\.s64 = 1;.*?"
        r"PPC_STORE_U32\(ctx\.r1\.u32 \+ 92, ctx\.r11\.u32\);.*?"
        r"ctx\.r5\.u64 = ctx\.r30\.u64;.*?ctx\.r4\.s64 = 0;.*?"
        r"ctx\.r3\.s64 = 255;.*?ctx\.lr = 0x84BE9A6C;\s*"
        r"__imp__XamShowMessageBoxUIEx",
        message_event_body,
        re.DOTALL,
    )
    assert re.search(
        r"PPC_STORE_U32\(ctx\.r1\.u32 \+ 96, ctx\.r3\.u32\);.*?"
        r"ctx\.cr6\.compare<uint32_t>\(ctx\.r3\.u32, 997, ctx\.xer\);.*?"
        r"ctx\.r5\.s64 = 1;.*?"
        r"ctx\.r4\.s64 = ctx\.r1\.s64 \+ 96;.*?"
        r"ctx\.r3\.s64 = ctx\.r1\.s64 \+ 112;.*?"
        r"ctx\.lr = 0x84BE9A88;\s*sub_84BE9230",
        message_event_body,
        re.DOTALL,
    )
    assert "PPC_LOAD_U32(ctx.r1.u32 + 104)" not in message_event_body
    assert "PPC_LOAD_U32(ctx.r1.u32 + 108)" not in message_event_body

    _, _, _, message_parent_body = find_function_body(
        "sub_84BE9B20", source_texts
    )
    assert re.search(
        r"ctx\.r5\.s64 = 1;.*?"
        r"ctx\.r4\.s64 = ctx\.r1\.s64 \+ 192;.*?"
        r"ctx\.r3\.s64 = ctx\.r1\.s64 \+ 256;.*?"
        r"ctx\.lr = 0x84BE9CE0;\s*sub_84BE99E0",
        message_parent_body,
        re.DOTALL,
    )

    _, _, _, overlapped_consumer_body = find_function_body(
        "sub_84BE9230", source_texts
    )
    assert re.search(
        r"ctx\.r11\.u64 = PPC_LOAD_U32\(ctx\.r31\.u32 \+ 0\);.*?"
        r"ctx\.cr6\.compare<uint32_t>\(ctx\.r11\.u32, 997, ctx\.xer\);.*?"
        r"ctx\.cr6\.compare<int32_t>\(ctx\.r5\.s32, 0, ctx\.xer\);.*?"
        r"ctx\.r3\.u64 = PPC_LOAD_U32\(ctx\.r31\.u32 \+ 12\);.*?"
        r"ctx\.r4\.s64 = -1;.*?ctx\.lr = 0x84BE9274;\s*"
        r"sub_84BE7130",
        overlapped_consumer_body,
        re.DOTALL,
    )
    assert re.search(
        r"ctx\.cr6\.compare<uint32_t>\(ctx\.r3\.u32, 258, ctx\.xer\);.*?"
        r"ctx\.r3\.s64 = 996;",
        overlapped_consumer_body,
        re.DOTALL,
    )
    assert re.search(
        r"ctx\.r11\.u64 = PPC_LOAD_U32\(ctx\.r31\.u32 \+ 4\);.*?"
        r"PPC_STORE_U32\(ctx\.r30\.u32 \+ 0, ctx\.r11\.u32\);.*?"
        r"ctx\.r3\.u64 = PPC_LOAD_U32\(ctx\.r31\.u32 \+ 0\);",
        overlapped_consumer_body,
        re.DOTALL,
    )

    xam_ui_path = XENIA / "src/xenia/kernel/xam/xam_ui.cc"
    xam_table_path = XENIA / "src/xenia/kernel/xam/xam_table.inc"
    xenia_kernel_state_path = XENIA / "src/xenia/kernel/kernel_state.cc"
    xenia_xbox_path = XENIA / "src/xenia/xbox.h"
    xam_ui_source = xam_ui_path.read_text(encoding="utf-8")
    xam_table_source = xam_table_path.read_text(encoding="utf-8")
    xenia_kernel_state_source = xenia_kernel_state_path.read_text(
        encoding="utf-8"
    )
    xenia_xbox_source = xenia_xbox_path.read_text(encoding="utf-8")
    assert xam_ui_source.count("dword_result_t XamShowMessageBoxUI_entry(") == 1
    assert "DECLARE_XAM_EXPORT1(XamShowMessageBoxUI, kUI, kImplemented);" in (
        xam_ui_source
    )
    assert "XamShowMessageBoxUIEx" not in xam_ui_source
    assert "*result_ptr = dialog->chosen_button();" in xam_ui_source
    assert "// Auto-pick the focused button." in xam_ui_source
    assert xam_table_source.count("XamShowMessageBoxUIEx") == 1
    assert re.search(
        r"0x000002DC, XamShowMessageBoxUIEx,\s+kFunction",
        xam_table_source,
    )
    assert re.search(
        r"struct XAM_OVERLAPPED \{\s*"
        r"xe::be<uint32_t> result;\s*// 0x0\s*"
        r"xe::be<uint32_t> length;\s*// 0x4\s*"
        r"xe::be<uint32_t> context;\s*// 0x8\s*"
        r"xe::be<uint32_t> event;\s*// 0xC\s*"
        r"xe::be<uint32_t> completion_routine;\s*// 0x10\s*"
        r"xe::be<uint32_t> completion_context;\s*// 0x14\s*"
        r"xe::be<uint32_t> extended_error;\s*// 0x18\s*\};",
        xenia_xbox_source,
    )
    assert "#define X_ERROR_IO_PENDING" in xenia_xbox_source
    assert re.search(
        r"XOverlappedSetResult\(ptr, X_ERROR_IO_PENDING\);.*?"
        r"XOverlappedSetContext\(ptr, XThread::GetCurrentThreadHandle\(\)\);",
        xenia_kernel_state_source,
        re.DOTALL,
    )
    assert re.search(
        r"XOverlappedSetResult\(ptr, result\);.*?"
        r"XOverlappedSetExtendedError\(ptr, extended_error\);.*?"
        r"XOverlappedSetLength\(ptr, length\);.*?"
        r"X_HANDLE event_handle = XOverlappedGetEvent\(ptr\);.*?"
        r"ev->Set\(0, false\);",
        xenia_kernel_state_source,
        re.DOTALL,
    )

    thread_create_row = thread_create_rows[0]
    assert thread_create_row["name"] == "ExCreateThread"
    assert len(thread_create_row["calls"]) == 1
    thread_create_call = thread_create_row["calls"][0]
    assert thread_create_call["call_address"] == "0x84BF108C"
    assert thread_create_call["caller"] == "sub_84BF1048"
    assert thread_create_call["return_address"] == "0x84BF1090"

    _, _, _, frontier_thread_wrapper = find_function_body(
        "sub_84BF1048", source_texts
    )
    assert re.search(
        r"ctx\.r10\.u64 = ctx\.r5\.u64;.*?"
        r"ctx\.r5\.u64 = ctx\.r9\.u64;.*?"
        r"ctx\.r9\.u64 = .*?ctx\.r7\.u32.*?& 0x1;.*?"
        r"ctx\.cr6\.compare<int32_t>\(ctx\.r8\.s32, -1, ctx\.xer\);.*?"
        r"ctx\.r8\.u64 = ctx\.r6\.u64;.*?"
        r"ctx\.r7\.u64 = ctx\.r10\.u64;.*?"
        r"ctx\.r6\.s64 = ctx\.r11\.s64 \+ 10544;.*?"
        r"ctx\.r3\.s64 = ctx\.r1\.s64 \+ 80;.*?"
        r"ctx\.lr = 0x84BF1090;\s*__imp__ExCreateThread",
        frontier_thread_wrapper,
        re.DOTALL,
    )
    assert re.search(
        r"ctx\.cr0\.compare<int32_t>\(ctx\.r3\.s32, 0, ctx\.xer\);.*?"
        r"ctx\.lr = 0x84BF109C;\s*sub_84BF0D58.*?"
        r"ctx\.r3\.s64 = 0;.*?"
        r"ctx\.r3\.u64 = PPC_LOAD_U32\(ctx\.r1\.u32 \+ 80\);",
        frontier_thread_wrapper,
        re.DOTALL,
    )
    assert ((-2067857408 + 10544) & 0xFFFFFFFF) == 0x84BF2930

    _, _, _, frontier_thread_tail = find_function_body(
        "sub_84BE84A0", source_texts
    )
    assert re.search(
        r"ctx\.r9\.u64 = ctx\.r8\.u64;.*?"
        r"ctx\.r8\.s64 = -1;.*?sub_84BF1048\(ctx, base\);\s*return;",
        frontier_thread_tail,
        re.DOTALL,
    )

    _, _, _, frontier_thread_builder = find_function_body(
        "sub_84B578D8", source_texts
    )
    assert re.search(
        r"ctx\.r31\.u64 = ctx\.r3\.u64;.*?"
        r"ctx\.r4\.u64 = ctx\.r8\.u64;.*?"
        r"ctx\.r8\.s64 = ctx\.r1\.s64 \+ 80;.*?"
        r"PPC_STORE_U32\(ctx\.r31\.u32 \+ 20, ctx\.r5\.u32\);.*?"
        r"ctx\.r7\.s64 = 0;.*?"
        r"PPC_STORE_U32\(ctx\.r31\.u32 \+ 8, ctx\.r11\.u32\);.*?"
        r"PPC_STORE_U32\(ctx\.r31\.u32 \+ 24, ctx\.r6\.u32\);.*?"
        r"ctx\.r3\.s64 = 0;.*?ctx\.r6\.u64 = ctx\.r31\.u64;.*?"
        r"PPC_STORE_U32\(ctx\.r31\.u32 \+ 16, ctx\.r31\.u32\);.*?"
        r"ctx\.r5\.s64 = ctx\.r11\.s64 \+ 30856;.*?"
        r"PPC_STORE_U32\(ctx\.r31\.u32 \+ 32, ctx\.r10\.u32\);.*?"
        r"PPC_STORE_U32\(ctx\.r31\.u32 \+ 28, ctx\.r9\.u32\);.*?"
        r"ctx\.lr = 0x84B5792C;\s*sub_84BE84A0",
        frontier_thread_builder,
        re.DOTALL,
    )
    assert re.search(
        r"PPC_STORE_U32\(ctx\.r31\.u32 \+ 4, ctx\.r3\.u32\);.*?"
        r"ctx\.r11\.s64 = ctx\.r11\.s64 - ctx\.r3\.s64;",
        frontier_thread_builder,
        re.DOTALL,
    )
    assert ((-2068512768 + 30856) & 0xFFFFFFFF) == 0x84B57888

    _, _, _, frontier_thread_parent = find_function_body(
        "sub_84679E00", source_texts
    )
    assert re.search(
        r"ctx\.r8\.s64 = 65536;.*?ctx\.r4\.s64 = ctx\.r11\.s64 \+ 8564;.*?"
        r"ctx\.r9\.s64 = 0;.*?ctx\.r8\.u64 = ctx\.r8\.u64 \| 49152;.*?"
        r"ctx\.r7\.s64 = 128;.*?ctx\.r6\.u64 = ctx\.r31\.u64;.*?"
        r"ctx\.r5\.s64 = 0;.*?ctx\.r3\.u64 = ctx\.r31\.u64;.*?"
        r"ctx\.lr = 0x84679E80;\s*sub_84B578D8",
        frontier_thread_parent,
        re.DOTALL,
    )
    assert ((-2075131904 + 8564) & 0xFFFFFFFF) == 0x84502174
    assert ((-2113929216 + 18132) & 0xFFFFFFFF) == 0x820046D4

    nonfrontier_thread_calls = extract_calls(
        "sub_84BF7340", "ExCreateThread", source_texts
    )
    assert len(nonfrontier_thread_calls) == 1
    assert nonfrontier_thread_calls[0]["call_address"] == "0x84BF759C"
    assert nonfrontier_thread_calls[0]["return_address"] == "0x84BF75A0"
    _, _, _, nonfrontier_thread_body = find_function_body(
        "sub_84BF7340", source_texts
    )
    assert re.search(
        r"ctx\.r27\.s64 = 1;.*?loc_84BF754C:.*?"
        r"ctx\.r7\.s64 = ctx\.r10\.s64 \+ 28584;.*?"
        r"ctx\.r7\.s64 = ctx\.r11\.s64 \+ 28384;.*?"
        r"ctx\.r11\.u64 = .*?ctx\.r27\.u32 <<.*?"
        r"ctx\.r9\.u64 = ctx\.r27\.u64;.*?"
        r"ctx\.r8\.s64 = 0;.*?ctx\.r6\.s64 = 0;.*?"
        r"ctx\.r5\.s64 = 0;.*?ctx\.r4\.s64 = 0;.*?"
        r"ctx\.r3\.s64 = ctx\.r1\.s64 \+ 84;.*?"
        r"ctx\.r9\.u64 = .*?& 0xFF000000.*?"
        r"ctx\.lr = 0x84BF75A0;\s*__imp__ExCreateThread",
        nonfrontier_thread_body,
        re.DOTALL,
    )
    assert re.search(
        r"ctx\.cr6\.compare<int32_t>\(ctx\.r3\.s32, 0, ctx\.xer\);.*?"
        r"ctx\.r4\.u64 = PPC_LOAD_U32\(ctx\.r28\.u32 \+ 2264\);.*?"
        r"ctx\.r3\.u64 = PPC_LOAD_U32\(ctx\.r1\.u32 \+ 84\);.*?"
        r"ctx\.lr = 0x84BF75B8;\s*__imp__ObReferenceObjectByHandle.*?"
        r"ctx\.lr = 0x84BF75C4;\s*__imp__KeSetBasePriorityThread.*?"
        r"ctx\.lr = 0x84BF75CC;\s*__imp__KeResumeThread.*?"
        r"ctx\.lr = 0x84BF75D4;\s*__imp__ObDereferenceObject",
        nonfrontier_thread_body,
        re.DOTALL,
    )
    assert ((-2067857408 + 28384) & 0xFFFFFFFF) == 0x84BF6EE0
    assert ((-2067857408 + 28584) & 0xFFFFFFFF) == 0x84BF6FA8

    exthread_slot = next(
        row for row in imported_data_frontier["slots"]
        if row["name"] == "ExThreadObjectType"
    )
    assert exthread_slot["slot"] == "0x820008D8"
    assert exthread_slot["raw_be32"] == "0x0001001B"
    assert exthread_slot["bootstrap_state"] == (
        "preserved_retail_ordinal_outside_frontier"
    )
    assert exthread_slot["frontier_consumers"] == []

    xenia_threading_path = (
        XENIA / "src/xenia/kernel/xboxkrnl/xboxkrnl_threading.cc"
    )
    xenia_xthread_path = XENIA / "src/xenia/kernel/xthread.cc"
    xenia_xthread_header_path = XENIA / "src/xenia/kernel/xthread.h"
    xenia_thread_table_path = (
        XENIA / "src/xenia/kernel/xboxkrnl/xboxkrnl_table.inc"
    )
    xenia_threading_source = xenia_threading_path.read_text(encoding="utf-8")
    xenia_xthread_source = xenia_xthread_path.read_text(encoding="utf-8")
    xenia_xthread_header = xenia_xthread_header_path.read_text(encoding="utf-8")
    xenia_thread_table = xenia_thread_table_path.read_text(encoding="utf-8")
    assert xenia_thread_table.count("ExCreateThread") == 1
    assert re.search(
        r"ExCreateThread_entry\(lpdword_t handle_ptr, dword_t stack_size,\s*"
        r"lpdword_t thread_id_ptr,\s*dword_t xapi_thread_startup,\s*"
        r"lpvoid_t start_address,\s*lpvoid_t start_context,\s*"
        r"dword_t creation_flags\)",
        xenia_threading_source,
    )
    assert re.search(
        r"actual_stack_size\s*=\s*std::max", xenia_threading_source
    )
    assert "new XThread(kernel_state(), actual_stack_size" in (
        xenia_threading_source
    )
    assert "X_STATUS result = thread->Create();" in xenia_threading_source
    assert "if (creation_flags & 0x80)" in xenia_threading_source
    assert "*handle_ptr = thread->guest_object();" in xenia_threading_source
    assert "*handle_ptr = thread->handle();" in xenia_threading_source
    assert "*thread_id_ptr = thread->thread_id();" in xenia_threading_source
    assert "constexpr uint32_t X_CREATE_SUSPENDED = 0x00000001;" in (
        xenia_xthread_header
    )
    assert "static_assert_size(X_KTHREAD, 0xAB0);" in xenia_xthread_header
    for required_thread_step in [
        "CreateNative<X_KTHREAD>()", "AllocateStack(creation_params_.stack_size)",
        "SystemHeapAlloc(scratch_size_)", "SystemHeapAlloc(tls_total_size_)",
        "SystemHeapAlloc(0x2D8)", "new cpu::ThreadState",
        "InitializeGuestObject()", "RetainHandle()",
        "xe::threading::Thread::Create", "SetActiveCpu(cpu_index)",
        "OnThreadCreated", "thread_->Resume()",
    ]:
        assert required_thread_step in xenia_xthread_source
    _, _, _, wait_body = find_function_body("sub_84BF0E08", source_texts)
    assert re.search(
        r"ctx\.r6\.u64 = ctx\.r30\.u64;.*?"
        r"ctx\.r5\.u64 = ctx\.r29\.u64;.*?"
        r"ctx\.r4\.s64 = 1;.*?ctx\.r3\.u64 = ctx\.r31\.u64;.*?"
        r"ctx\.lr = 0x84BF0E40;\s*__imp__NtWaitForSingleObjectEx",
        wait_body,
        re.DOTALL,
    )
    _, _, _, timeout_body = find_function_body("sub_84BF1028", source_texts)
    assert re.search(
        r"ctx\.cr6\.compare<int32_t>\(ctx\.r4\.s32, -1, ctx\.xer\);.*?"
        r"ctx\.r3\.s64 = 0;.*?ctx\.r11\.u64 = ctx\.r4\.u64 & "
        r"0xFFFFFFFF;.*?ctx\.r11\.s64 = ctx\.r11\.s64 \* -10000;.*?"
        r"PPC_STORE_U64\(ctx\.r3\.u32 \+ 0, ctx\.r11\.u64\);",
        timeout_body,
        re.DOTALL,
    )

    status_helper = "sub_84BF0D58"
    status_helper_callers = sorted(
        caller
        for caller in active
        if generated_calls[caller].count(status_helper) != 0
    )
    assert status_helper_callers == [
        "sub_84BE7038", "sub_84BF0E08", "sub_84BF1048",
    ]
    assert all(generated_calls[caller].count(status_helper) == 1
               for caller in status_helper_callers)

    _, _, _, status_helper_body = find_function_body(
        status_helper, source_texts
    )
    status_import_marker = (
        "ctx.lr = 0x84BF0D68;\n"
        "\t__imp__RtlNtStatusToDosError(ctx, base);"
    )
    status_import_offset = status_helper_body.find(status_import_marker)
    assert status_import_offset >= 0
    assert status_helper_body.find(
        status_import_marker, status_import_offset + 1
    ) < 0
    assert not re.search(
        r"ctx\.r3\.[us][0-9]+\s*=", status_helper_body[:status_import_offset]
    )

    status_caller_specs = [
        {
            "caller": "sub_84BE7038",
            "upstream_import": "NtCreateEvent",
            "upstream_call_address": "0x84BE7088",
            "upstream_return_address": "0x84BE708C",
            "helper_call_address": "0x84BE70B4",
            "helper_return_address": "0x84BE70B8",
            "current_negative_statuses": ["0xC0000017"],
            "current_negative_status_names": ["X_STATUS_NO_MEMORY"],
            "runtime_reason": (
                "the bounded event table returns X_STATUS_NO_MEMORY only "
                "when all 64 event slots are active"
            ),
        },
        {
            "caller": "sub_84BF0E08",
            "upstream_import": "NtWaitForSingleObjectEx",
            "upstream_call_address": "0x84BF0E3C",
            "upstream_return_address": "0x84BF0E40",
            "helper_call_address": "0x84BF0E5C",
            "helper_return_address": "0x84BF0E60",
            "current_negative_statuses": ["0xC0000008"],
            "current_negative_status_names": ["X_STATUS_INVALID_HANDLE"],
            "runtime_reason": (
                "the bounded wait returns X_STATUS_INVALID_HANDLE for an "
                "unknown or stale adapter-owned event handle"
            ),
        },
        {
            "caller": "sub_84BF1048",
            "upstream_import": "ExCreateThread",
            "upstream_call_address": "0x84BF108C",
            "upstream_return_address": "0x84BF1090",
            "helper_call_address": "0x84BF1098",
            "helper_return_address": "0x84BF109C",
            "current_negative_statuses": [],
            "current_negative_status_names": [],
            "runtime_reason": (
                "ExCreateThread stops at a typed thread_create_requested "
                "boundary, so generated code cannot consume a fabricated "
                "NTSTATUS or reach this helper"
            ),
        },
    ]
    for spec in status_caller_specs:
        _, _, _, caller_body = find_function_body(spec["caller"], source_texts)
        upstream_marker = (
            f"ctx.lr = {spec['upstream_return_address']};\n"
            f"\t__imp__{spec['upstream_import']}(ctx, base);"
        )
        helper_marker = (
            f"ctx.lr = {spec['helper_return_address']};\n"
            f"\t{status_helper}(ctx, base);"
        )
        upstream_offset = caller_body.find(upstream_marker)
        helper_offset = caller_body.find(helper_marker)
        assert 0 <= upstream_offset < helper_offset
        passthrough = caller_body[
            upstream_offset + len(upstream_marker):helper_offset
        ]
        assert "ctx.cr0.compare<int32_t>(ctx.r3.s32, 0" in passthrough
        if spec["helper_call_address"] in {"0x84BE70B4", "0x84BF0E5C"}:
            failure_label = (
                "loc_" + str(spec["helper_call_address"])[2:] + ":"
            )
            label_offset = caller_body.find(failure_label, upstream_offset)
            assert 0 <= label_offset < helper_offset
            failure_edge = caller_body[
                label_offset + len(failure_label):helper_offset
            ]
        else:
            failure_condition = "if (!ctx.cr0.lt) goto loc_84BF10A4;"
            condition_offset = caller_body.find(
                failure_condition, upstream_offset, helper_offset
            )
            assert condition_offset >= 0
            failure_edge = caller_body[
                condition_offset + len(failure_condition):helper_offset
            ]
        assert not re.search(r"ctx\.r3\.[us][0-9]+\s*=", failure_edge)

    xenia_error_path = (
        XENIA / "src/xenia/kernel/xboxkrnl/xboxkrnl_error.cc"
    )
    xenia_error_source = xenia_error_path.read_text(encoding="utf-8")
    assert "0x00000006,  // 0xC0000008" in xenia_error_source
    assert "0x00000008,  // 0xC0000017" in xenia_error_source
    assert "return 317;  // ERROR_MR_MID_NOT_FOUND" in xenia_error_source
    xenia_license_path = XENIA / "LICENSE"
    xenia_license = xenia_license_path.read_text(encoding="utf-8")
    assert "Redistribution and use in source and binary forms" in xenia_license

    runtime_source = (
        ROOT / "src/static_runtime/apf_boot_leaf_adapters.c"
    ).read_text(encoding="utf-8")
    assert re.search(
        r"case VC_APF_X_STATUS_INVALID_HANDLE:\s*"
        r"dos_error = VC_APF_X_ERROR_INVALID_HANDLE;",
        runtime_source,
    )
    assert re.search(
        r"case VC_APF_X_STATUS_NO_MEMORY:\s*"
        r"dos_error = VC_APF_X_ERROR_NOT_ENOUGH_MEMORY;",
        runtime_source,
    )
    assert "never guess ERROR_MR_MID_NOT_FOUND" in runtime_source

    rtl_ntstatus_mapping = {
        "thunk_address": "0x84D0864C",
        "direct_call_address": "0x84BF0D64",
        "return_address": "0x84BF0D68",
        "helper_address": "0x84BF0D58",
        "exact_callsite_gated": True,
        "helper_preserves_input_r3_until_import": True,
        "frontier_scope": {
            "source": "reports/static_recomp/apf2k8_boot_indirect_frontier.json",
            "total_nodes_including_imports": 458,
            "descended_generated_nodes": 426,
            "helper_caller_count": len(status_helper_callers),
            "path_sensitive_boot_trace": False,
            "title_main_descended_or_executed": False,
        },
        "augmented_frontier_helper_callers": status_caller_specs,
        "current_resumable_negative_status_set": [
            "0xC0000008", "0xC0000017",
        ],
        "bounded_mappings": [
            {
                "ntstatus": "0xC0000008",
                "ntstatus_name": "X_STATUS_INVALID_HANDLE",
                "dos_error": "0x00000006",
                "dos_error_name": "ERROR_INVALID_HANDLE",
            },
            {
                "ntstatus": "0xC0000017",
                "ntstatus_name": "X_STATUS_NO_MEMORY",
                "dos_error": "0x00000008",
                "dos_error_name": "ERROR_NOT_ENOUGH_MEMORY",
            },
        ],
        "mapping_scope": (
            "fail-closed two-entry mapping, not a complete NTSTATUS table"
        ),
        "unknown_or_wrong_callsite_status": (
            "unsupported_variant; raw low 32-bit input is recorded before "
            "fatal-stop r3 scrubbing and generated guest code may not resume"
        ),
        "unknown_ntstatus_treated_as_success": False,
        "error_mr_mid_not_found_synthesized": False,
        "input_abi": (
            "consume the low 32-bit NTSTATUS from r3 whether its incoming "
            "64-bit representation is sign- or zero-extended"
        ),
        "result_abi": (
            "store the 32-bit ULONG result through int32_t into 64-bit r3; "
            "the proved positive errors therefore have zero upper 32 bits"
        ),
        "microsoft_contract": (
            "https://learn.microsoft.com/en-us/windows-hardware/drivers/"
            "ddi/ntifs/nf-ntifs-rtlntstatustodoserror"
        ),
        "pinned_xenia_provenance": {
            "commit": git_head(XENIA),
            "mapping_source": "src/xenia/kernel/xboxkrnl/xboxkrnl_error.cc",
            "mapping_source_sha256": sha256(xenia_error_path),
            "license": "BSD-3-Clause",
            "license_path": "LICENSE",
            "license_sha256": sha256(xenia_license_path),
            "complete_table_copied": False,
            "fallback_317_adopted": False,
        },
    }

    message_box_ui = {
        "name": "XamShowMessageBoxUIEx",
        "thunk_address": "0x84D07EDC",
        "direct_call_address": "0x84BE9A68",
        "return_address": "0x84BE9A6C",
        "caller": "sub_84BE99E0",
        "parent_caller": "sub_84BE9B20",
        "sole_direct_import_site": True,
        "register_arguments": {
            "r3": "255 (exact caller value)",
            "r4": "NULL title",
            "r5": "UTF-16 message at current r1+432",
            "r6": "1 button",
            "r7": "one big-endian pointer cell at current r1+204",
            "r8": "active button 0",
            "r9": "flags 1",
            "r10": "opaque UIEx argument 1",
        },
        "stack_arguments": {
            "r1+84": "big-endian pointer to eight-byte object at r1+104",
            "r1+92": "big-endian pointer to XAM_OVERLAPPED at r1+112",
        },
        "caller_pointer_graph": {
            "message": (
                "sub_84BE9B20 parent r1+256; sub_84BE99E0 current r1+432"
            ),
            "button_pointer_cell": "current r1+204",
            "button": (
                "sub_84BE9B20 parent r1+192; sub_84BE99E0 current r1+368"
            ),
            "result_object": "current r1+104",
            "overlapped": "current r1+112",
            "event_handle_cell": "current r1+124 = overlapped+12",
        },
        "input_buffers": {
            "message": {
                "format": "big-endian UTF-16 with required NUL",
                "capacity_code_units_including_nul": 256,
                "maximum_non_nul_code_units": 255,
            },
            "button": {
                "format": "big-endian UTF-16 with required NUL",
                "capacity_code_units_including_nul": 32,
                "maximum_non_nul_code_units": 31,
            },
            "host_request_copy": (
                "host-endian UTF-16, bounded, NUL-terminated, one button"
            ),
        },
        "opaque_result_object": {
            "address": "r1+104",
            "size": 8,
            "initial_state": "two zero big-endian dwords",
            "reachable_reads_after_import": 0,
            "adapter_writes_selection": False,
            "policy": (
                "validate and preserve; exact UIEx layout is not proved and the "
                "reached APF caller never consumes it"
            ),
        },
        "xam_overlapped": {
            "address": "r1+112",
            "size": 28,
            "layout": {
                "0x00": "big-endian result",
                "0x04": "big-endian length",
                "0x08": "big-endian context",
                "0x0C": "big-endian event handle",
                "0x10": "big-endian completion routine",
                "0x14": "big-endian completion context",
                "0x18": "big-endian extended error",
            },
            "initial_state": (
                "all zero except the adapter-owned synchronization event at +0x0C"
            ),
            "request_write": "result=997 (X_ERROR_IO_PENDING) only",
            "completion_writes": (
                "result=0, length=0, extended_error=0; signal exact event"
            ),
            "context_policy": (
                "preserve zero; no guest thread handle is fabricated and this "
                "APF completion path has no completion routine"
            ),
        },
        "immediate_consumer": {
            "import_result_storage": "current r1+96",
            "pending_value": 997,
            "pending_branch": (
                "call sub_84BE9230(overlapped=r1+112, length_out=r1+96, wait=1)"
            ),
            "helper_address": "0x84BE9230",
            "helper_semantics": (
                "if result is 997, optionally wait on event+12; timeout 258 "
                "becomes 996; otherwise copy length+4 to output and return result+0"
            ),
            "helper_return_consumed_by_caller": False,
            "event_close_after_helper": {
                "call_address": "0x84BE9A8C",
                "return_address": "0x84BE9A90",
            },
        },
        "request_boundary": {
            "dispatch_status": "ui_requested",
            "import_result_before_pause": 997,
            "host_thread_blocks": False,
            "automatic_or_default_selection": False,
            "explicit_completion_selection": 0,
            "maximum_pending_requests": 1,
            "requesting_guest_thread_latched": True,
            "resume_context": (
                "exact post-import context with r3=997; completed guest "
                "overlapped and signaled event are visible before continuation"
            ),
        },
        "failure_policy": {
            "wrong_callsite_or_argument_shape": "unsupported_variant",
            "invalid_guest_pointer": "memory_fault",
            "changed_result_overlapped_or_event_state": "guest_state",
            "failed_request_or_completion_is_transactional": True,
        },
        "pinned_xenia_provenance": {
            "commit": git_head(XENIA),
            "regular_message_box_source": "src/xenia/kernel/xam/xam_ui.cc",
            "regular_message_box_source_sha256": sha256(xam_ui_path),
            "kernel_overlapped_source": "src/xenia/kernel/kernel_state.cc",
            "kernel_overlapped_source_sha256": sha256(
                xenia_kernel_state_path
            ),
            "overlapped_layout_source": "src/xenia/xbox.h",
            "overlapped_layout_source_sha256": sha256(xenia_xbox_path),
            "ui_export_table_source": "src/xenia/kernel/xam/xam_table.inc",
            "ui_export_table_source_sha256": sha256(xam_table_path),
            "regular_message_box_implemented": True,
            "regular_dialog_completion_uses_explicit_choice": True,
            "regular_headless_mode_auto_selects_active_button": True,
            "ui_ex_export_present": True,
            "ui_ex_implementation_present": False,
            "deferred_overlapped_sets_pending_and_thread_context": True,
            "completion_sets_result_extended_error_length_and_event": True,
        },
        "evidence_limit": (
            "Xenia supplies the regular XamShowMessageBoxUI behavior and the "
            "shared overlapped mechanics, but does not implement UIEx; r10 and "
            "the eight-byte result object therefore remain semantically unnamed"
        ),
        "guest_title_code_executed": False,
        "frontier_is_path_sensitive_boot_trace": False,
    }

    thread_creation_boundary = {
        "dispatch_status": "thread_create_requested",
        "resumable_without_scheduler_lifecycle": False,
        "frontier_import": {
            "thunk_address": "0x84D0876C",
            "call_address": "0x84BF108C",
            "return_address": "0x84BF1090",
            "direct_caller": "sub_84BF1048",
            "upstream_chain": [
                "sub_84679E00", "sub_84B578D8", "sub_84BE84A0",
                "sub_84BF1048",
            ],
            "sole_direct_site_in_458_node_frontier": True,
        },
        "exact_xenon_abi": {
            "r3": "handle output at current r1+80",
            "r4": "requested stack size 0x0001C000",
            "r5": "thread ID output at current r1+176",
            "r6": "XAPI startup trampoline 0x84BF2930",
            "r7": "start address 0x84B57888",
            "r8": "dynamic start-context object",
            "r9": "creation flags 0 (not suspended; no processor mask)",
            "result": "signed NTSTATUS in r3",
        },
        "wrapper_argument_transform": {
            "handle_pointer": "new 96-byte wrapper frame r1+80",
            "thread_id_pointer": (
                "sub_84B578D8 r1+80, which is wrapper-current r1+176"
            ),
            "xapi_thread_startup": "constant 0x84BF2930",
            "creation_flags_bit_0": "incoming r7 bit 2; exact frontier value 0",
            "processor_mask": (
                "incoming r8=-1 suppresses the optional top-byte CPU mask"
            ),
        },
        "start_context_candidate": {
            "size_preflighted": 40,
            "layout": {
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
            },
            "confidence": (
                "exact generated upstream writes for this frontier shape; "
                "semantic field names beyond handle/self remain unproved"
            ),
        },
        "immediate_consumer": {
            "signed_status_test": "negative branches to sub_84BF0D58",
            "failure_conversion": (
                "RtlNtStatusToDosError then wrapper returns handle value 0"
            ),
            "success_handle_load": "big-endian handle from wrapper r1+80",
            "upstream_handle_store": "start-context +0x04",
            "generated_continuation_allowed_by_adapter": False,
        },
        "request_contract": {
            "maximum_pending_requests": 1,
            "requesting_guest_thread_latched": True,
            "complete_ppc_integer_context_preserved": True,
            "handle_or_thread_id_output_written": False,
            "ntstatus_returned_to_guest": False,
            "guest_thread_object_allocated": False,
            "guest_stack_allocated": False,
            "guest_tls_pcr_or_cpu_context_allocated": False,
            "host_thread_created": False,
            "guest_entry_executed": False,
            "completion_api_available": False,
            "reason_no_completion": (
                "the future scheduler must atomically accept ownership of all "
                "thread resources before success and either enqueue this "
                "creation_flags=0 thread or return a real failure NTSTATUS"
            ),
        },
        "failure_policy": {
            "wrong_frontier_shape_or_nonfrontier_lr": "unsupported_variant",
            "invalid_output_or_context_span": "memory_fault",
            "changed_start_context_candidate": "guest_state",
            "request_publication_is_transactional": True,
        },
        "other_known_direct_site": {
            "in_458_node_frontier": False,
            "caller": "sub_84BF7340",
            "call_address": "0x84BF759C",
            "return_address": "0x84BF75A0",
            "loop_count": 6,
            "stack_size": 0,
            "thread_id_pointer": "NULL",
            "xapi_thread_startup": "NULL",
            "start_addresses": ["0x84BF6EE0", "0x84BF6FA8"],
            "start_context": "NULL",
            "creation_flags": (
                "X_CREATE_SUSPENDED plus one top-byte processor-affinity bit"
            ),
            "downstream_consumers": [
                "ObReferenceObjectByHandle",
                "KeSetBasePriorityThread",
                "KeResumeThread",
                "ObDereferenceObject",
            ],
            "adapter_policy": (
                "explicitly rejected by LR; no nonfrontier thread is created"
            ),
        },
        "pinned_xenia_provenance": {
            "commit": git_head(XENIA),
            "export_source": (
                "src/xenia/kernel/xboxkrnl/xboxkrnl_threading.cc"
            ),
            "export_source_sha256": sha256(xenia_threading_path),
            "thread_source": "src/xenia/kernel/xthread.cc",
            "thread_source_sha256": sha256(xenia_xthread_path),
            "thread_header": "src/xenia/kernel/xthread.h",
            "thread_header_sha256": sha256(xenia_xthread_header_path),
            "export_table": "src/xenia/kernel/xboxkrnl/xboxkrnl_table.inc",
            "export_table_sha256": sha256(xenia_thread_table_path),
            "x_kthread_size": "0xAB0",
            "x_create_suspended": "0x00000001",
            "allocates_guest_object_stack_scratch_tls_pcr_cpu_state": True,
            "creates_host_thread_suspended_before_guest_policy_resume": True,
            "returns_handle_and_optional_thread_id_only_after_create": True,
        },
        "imported_data_frontier_evidence": {
            "source": (
                "reports/static_recomp/apf2k8_imported_data_frontier.json"
            ),
            "source_sha256": sha256(IMPORTED_DATA_FRONTIER_PATH),
            "frontier_needed_slots_seeded": 2,
            "all_thirteen_slots_resolved": False,
            "ex_thread_object_type_slot": "0x820008D8",
            "ex_thread_object_type_runtime_state": (
                "preserved retail ordinal 0x0001001B, not a guest object-type "
                "pointer; classified outside the current frontier"
            ),
            "nonfrontier_consumer_dependency": (
                "sub_84BF7340 loads 0x820008D8 before "
                "ObReferenceObjectByHandle"
            ),
            "imported_data_files_modified": False,
        },
        "microsoft_threading_reference": (
            "https://learn.microsoft.com/en-us/windows/win32/dxtecharts/"
            "coding-for-multiple-cores"
        ),
        "guest_title_code_executed": False,
        "frontier_is_path_sensitive_boot_trace": False,
    }

    resumable_sites = sum(row["static_call_sites"] for row in implemented_rows)
    terminal_sites = sum(row["static_call_sites"] for row in terminal_rows)
    exception_sites = sum(row["static_call_sites"] for row in exception_rows)
    thread_create_sites = sum(
        row["static_call_sites"] for row in thread_create_rows
    )
    unsupported_sites = sum(row["static_call_sites"] for row in unsupported_rows)
    resumable_indirect_sites = sum(
        row["proved_indirect_static_sites"] for row in implemented_rows
    )
    assert resumable_sites == 76
    assert resumable_indirect_sites == 4
    assert terminal_sites == 8
    assert exception_sites == 2
    assert thread_create_sites == 1
    assert unsupported_sites == 0
    assert (resumable_sites + terminal_sites + exception_sites +
            thread_create_sites + unsupported_sites) == 87

    unresolved_indirect = []
    for site in indirect_frontier["original_indirect_sites"]:
        if site["classification"] != "unresolved_dynamic":
            continue
        unresolved_indirect.append(
            {
                "call_address": site["call_instruction_address"],
                "caller": site["caller"],
                "classification": "original_unresolved_dynamic",
                "portme": "// " + site["portme"],
                "source": site["ctr_source"],
            }
        )
    for site in indirect_frontier["augmented_frontier"][
        "newly_exposed_indirect_sites"
    ]:
        unresolved_indirect.append(
            {
                "call_address": site["call_instruction_address"],
                "caller": site["caller"],
                "classification": "second_wave_not_admitted",
                "portme": "// " + site["portme"],
                "source": site["ctr_source"],
            }
        )
    unresolved_indirect.sort(key=lambda row: row["call_address"])
    assert [int(row["call_address"], 16) for row in unresolved_indirect] == [
        0x8468CF4C, 0x84BDAA00, 0x84BDAFA0, 0x84BDDF90,
        0x84BEBDEC, 0x84BF0C94, 0x84BF198C,
    ]

    return {
        "schema": "apf2k8_boot_leaf_adapters/v7",
        "validation_date": "2026-07-11",
        "result": {
            "classified_frontier_import_count": (
                len(implemented_rows) + len(terminal_rows) +
                len(exception_rows) + len(thread_create_rows)
            ),
            "classified_static_call_site_count": (
                resumable_sites + terminal_sites + exception_sites +
                thread_create_sites
            ),
            "augmented_direct_static_call_site_count": 87,
            "proved_indirect_import_dispatch_site_count": 4,
            "total_classified_import_dispatch_site_count": 91,
            "all_non_ok_statuses_stop_immediate_guest_continuation": True,
            "dbgprint_implemented": True,
            "frontier_import_count": len(rows),
            "guest_title_code_executed": False,
            "normal_host_shell_links_adapter": False,
            "resumable_import_count": len(implemented_rows),
            "resumable_static_call_site_count": resumable_sites,
            "resumable_proved_indirect_dispatch_site_count": (
                resumable_indirect_sites
            ),
            "exception_required_import_count": len(exception_rows),
            "exception_required_static_call_site_count": exception_sites,
            "terminal_import_count": len(terminal_rows),
            "terminal_static_call_site_count": terminal_sites,
            "thread_create_required_import_count": len(thread_create_rows),
            "thread_create_required_static_call_site_count": (
                thread_create_sites
            ),
            "unsupported_frontier_import_count": len(unsupported_rows),
            "unsupported_static_call_site_count": unsupported_sites,
            "unresolved_indirect_runtime_surface_site_count": 7,
        },
        "inputs": {
            "generated_sources": generated_inputs,
            "local_sources": local_inputs,
            "pinned_xenia_commit": git_head(XENIA),
            "pinned_xenia_sources": xenia_inputs,
            "retail_xex_sha256": sha256(
                ROOT / "extracted/All-Pro Football 2K8 (USA)/default.xex"
            ),
        },
        "guest_abi": {
            "argument_registers": ["r3", "r4", "r5", "r6", "r7"],
            "integer_result_register": (
                "r3, sign-extended from 32 bits through all 64 bits"
            ),
            "pinned_xenia_result_extension": (
                "shim::ResultBase<T>::Store and SHIM_SET_RETURN_32 cast through "
                "int32_t before storing the 64-bit PPC r3"
            ),
            "narrowed_control_flow_effect": (
                "the reached APF consumers inspect s32/u32, so correcting the "
                "upper 32 bits does not change this bounded frontier's branches"
            ),
            "link_register_interpretation": (
                "linking direct calls set LR to return address (call=LR-4); three "
                "direct tail branches inherit LR and are recovered from their exact "
                "instruction addresses"
            ),
            "proved_indirect_import_dispatches": [
                call
                for row in implemented_rows
                for call in row["proved_indirect_dispatches"]
            ],
            "implemented_imports": implemented_rows,
            "exception_required_imports": exception_rows,
            "thread_create_required_imports": thread_create_rows,
            "terminal_imports": terminal_rows,
        },
        "explicit_configuration": {
            "all_values_required": True,
            "apf_retail_system_flags": xex_report["execution"]["system_flags_raw"],
            "apf_retail_system_flag_names": xex_report["execution"]["system_flags"],
            "apf_early_privilege_query": 10,
            "apf_early_privilege_query_mask": "0x00000400",
            "apf_retail_query_result": False,
            "av_pack_default": None,
            "language_default": None,
            "process_type_default": None,
            "secured_av_region_default": None,
            "user_video_flags_default": None,
            "vm_arena_default": None,
            "vm_backing_default": None,
            "vm_existing_ranges_default": None,
            "reason": (
                "Xenia's XGetAVPack value 6 is marked kStub, while its language "
                "and process type are emulator policy; both XConfig values are also "
                "mandatory inputs; the VM arena, backing, and existing maps "
                "are loader-owned inputs too, so the adapter guesses none of them."
            ),
        },
        "xconfig": {
            "exact_variants": [
                {
                    "buffer": "r1+84",
                    "buffer_size": 4,
                    "call_address": "0x84BE9B84",
                    "category": 2,
                    "required_size": "r1+80",
                    "setting": 2,
                    "value_source": "configured secured_av_region",
                },
                {
                    "buffer": "r1+88",
                    "buffer_size": 4,
                    "call_address": "0x84BE9BB4",
                    "category": 3,
                    "required_size": "r1+80",
                    "setting": 10,
                    "value_source": "configured user_video_flags",
                },
            ],
            "guest_status_on_success": "0x00000000",
            "output_endianness": "big-endian u32 value and big-endian u16 size 4",
            "preflight_policy": (
                "both disjoint aligned spans must be in bounds before either write"
            ),
            "unobserved_variant_status": "unsupported_variant; guest may not resume",
            "writes_per_successful_call": 2,
        },
        "dbg_print": {
            "call_address": "0x84BE9EB4",
            "return_address": "0x84BE9EB8",
            "format_address": "0x844D37B8",
            "format_rva": "0x024D37B8",
            "format_literal": "[XAPI RETURN VALUE] %d\n",
            "format_bytes_including_nul": 24,
            "format_hex_including_nul": (
                "5b584150492052455455524e2056414c55455d2025640a00"
            ),
            "decoded_pe_sha256": xex_report["inputs"][
                "decompressed_pe_sha256"
            ],
            "exact_abi": "r3=0x844D37B8; r4=one signed 32-bit decimal",
            "guest_memory_policy": (
                "all 24 bytes including NUL must be in bounds and byte-exact"
            ),
            "output_policy": (
                "record XAPI_RETURN_VALUE_S32 as a structured event; never pass "
                "guest bytes to a host format function"
            ),
            "success_result": "X_STATUS_SUCCESS (r3=0)",
            "other_callsite_or_format_status": "unsupported_variant",
            "mismatched_exact_address_bytes_status": "guest_state",
            "pinned_xenia_behavior": (
                "DbgPrint uses StackArgList and format_core, logs the formatted "
                "string, and returns X_STATUS_SUCCESS"
            ),
        },
        "rtl_image_xex_header_field": {
            "call_address": "0x84BF1888",
            "return_address": "0x84BF188C",
            "requested_key": "0x00020401",
            "requested_key_name": "XEX_HEADER_DEFAULT_HEAP_SIZE",
            "retail_optional_header_count": len(retail_options),
            "retail_optional_header_keys": [
                f"0x{key:08X}" for key, _ in retail_options
            ],
            "requested_key_present": False,
            "retail_prefix_bytes_parsed": 24 + len(retail_options) * 8,
            "dynamic_guest_header_pointer": "r3; never guessed",
            "identity_policy": (
                "bounds-check and match the complete fixed XEX2 prefix plus all "
                "15 key/value entries to the SHA-pinned retail header"
            ),
            "success_result": "NULL (r3=0) because the key is absent",
            "fabricated_guest_pointer_or_heap_value": False,
            "other_key_or_callsite_status": "unsupported_variant",
            "malformed_or_nonretail_prefix_status": "guest_state",
            "pinned_xenia_behavior": (
                "UserModule::GetOptHeader scans header_count entries and leaves "
                "the returned field value zero when the key is not found"
            ),
        },
        "rtl_init_ansi_string": {
            "direct_call_sites": ["0x84BF0BAC", "0x84BF0DD4"],
            "exact_callsite_abi": [
                {
                    "call_address": "0x84BF0BAC",
                    "caller": "sub_84BF0B88",
                    "destination": "r3 = r1+80",
                    "source": "r4 = caller's incoming r3",
                },
                {
                    "call_address": "0x84BF0DD4",
                    "caller": "sub_84BF0DB0",
                    "destination": "r3 = caller's incoming r4",
                    "source": "r4 = caller's incoming r5",
                },
            ],
            "guest_layout": {
                "0x00": "big-endian u16 Length",
                "0x02": "big-endian u16 MaximumLength",
                "0x04": "big-endian u32 Buffer guest pointer",
                "size": 8,
            },
            "null_source": "Length=0, MaximumLength=0, Buffer=0",
            "source_bound_policy": (
                "a NUL byte must occur before the declared guest-memory window or "
                "32-bit guest address space ends; otherwise memory_fault with no write"
            ),
            "long_string_policy": (
                "lengths above MAXUSHORT-1 saturate to Length=0xFFFE and "
                "MaximumLength=0xFFFF after a bounded terminating-NUL scan"
            ),
            "transactional_write": (
                "preflight the aligned 8-byte destination and complete the source "
                "scan before writing any descriptor byte"
            ),
            "pinned_xenia_layout_and_implementation": (
                "/media/noah/Storage/.codex-tmp/xenia-source/src/xenia/xbox.h:227 "
                "and src/xenia/kernel/xboxkrnl/xboxkrnl_rtl.cc:141"
            ),
            "pinned_xenia_long_string_divergence": (
                "Xenia casts host strlen to u16 and can wrap; the adapter follows "
                "Microsoft's MAXUSHORT-1 saturation contract"
            ),
            "microsoft_contract": (
                "https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/"
                "wdm/nf-wdm-rtlinitansistring"
            ),
        },
        "tls": {
            "allocation_slots": 2048,
            "failed_allocation_result": "0xFFFFFFFF",
            "free_clears_all_registered_guest_threads": True,
            "guest_thread_capacity_in_bounded_adapter": 64,
            "host_thread_local_storage_used": False,
            "invalid_or_unallocated_get_result": 0,
            "invalid_or_unallocated_set_result": 0,
            "scheduler_boundary": (
                "the future scheduler must attach persistent guest-thread objects and "
                "pass the currently scheduled object on every dispatch; host pthread "
                "identity is never treated as guest identity"
            ),
            "values_are_opaque_guest_u32": True,
        },
        "guest_memory": {
            "big_endian_ulong_loads": True,
            "big_endian_xconfig_ansi_and_critical_section_writes": True,
            "bounds_check_policy": "base/offset/length checked without 32-bit wrap",
            "memory_fault_is_fatal_dispatch_status": True,
            "writes_guest_memory": True,
        },
        "virtual_memory": {
            "direct_call_site_count": 19,
            "allocate_call_sites": vm_allocate_shapes,
            "free_call_sites": vm_free_shapes,
            "query_call_sites": vm_query_shapes,
            "all_calls_gated_by_exact_return_address": True,
            "dynamic_nozero_proof": (
                "sub_84BEDA38 initializes r24 to zero and never rewrites it; "
                "the 0x84BEE1CC path selects r24 or literal 0x00800000 before "
                "adding LARGE_PAGES|HEAP|COMMIT"
            ),
            "page_size": 65536,
            "page_size_provenance": (
                "all 11 APF allocation sites set X_MEM_LARGE_PAGES; pinned "
                "Xenia selects its 0x40000000 64 KiB guest-virtual heap"
            ),
            "pinned_xenia_large_heap": "[0x40000000, 0x7F000000)",
            "loader_configuration": {
                "arena_base_and_size_required": True,
                "writable_backing_exactly_arena_size_required": True,
                "existing_range_capacity": 16,
                "required_existing_range_kinds": [
                    "title_image", "static_dispatch", "import_thunks",
                ],
                "required_apf_coverage": {
                    "title_image": "[0x82000000, 0x85380000)",
                    "static_dispatch": "[0x85380000, 0x86133000)",
                    "import_thunks": "[0x84D07B6C, 0x84D09040)",
                },
                "core_ranges_must_not_overlap_arena": True,
                "other_mapping_intersections_exclude_whole_arena_pages": True,
                "defaults": None,
            },
            "ledger": {
                "maximum_pages": 16384,
                "maximum_allocations": 256,
                "collision_free_bottom_up_first_fit": True,
                "states": ["free", "reserved", "committed", "external"],
                "separate_from_title_dispatch_and_import_ranges": True,
                "release_requires_allocation_base": True,
                "decommit_preserves_reservation": True,
            },
            "allocation_semantics": {
                "base_rounding": "down to a 64 KiB page",
                "size_rounding": "up to a 64 KiB page",
                "commit_zero_gate": (
                    "match pinned Xenia: zero the complete rounded request "
                    "unless its first page was already committed or NOZERO is set"
                ),
                "nozero_preserves_newly_committed_backing": True,
                "fixed_commit_inside_reservation_supported": True,
                "commit_without_prior_reservation_supported": True,
                "unproved_flags_or_callsite_status": "unsupported_variant",
            },
            "query_layout": {
                "0x00": "big-endian u32 BaseAddress",
                "0x04": "big-endian u32 AllocationBase",
                "0x08": "big-endian u32 AllocationProtect",
                "0x0C": "big-endian u32 RegionSize",
                "0x10": "big-endian u32 State",
                "0x14": "big-endian u32 Protect",
                "0x18": "big-endian u32 Type",
                "size": 28,
            },
            "guest_failure_policy": (
                "proved ABI calls return an exact sign-extended NTSTATUS in r3; "
                "guest request failures do not become adapter-fatal statuses"
            ),
            "transactional_policy": (
                "preflight disjoint aligned BE pointer cells and the complete "
                "operation before any output or ledger mutation; writes occur "
                "only after a successful semantic operation"
            ),
            "pinned_xenia_sources": [
                "src/xenia/kernel/xboxkrnl/xboxkrnl_memory.cc",
                "src/xenia/memory.cc",
                "src/xenia/memory.h",
                "src/xenia/xbox.h",
            ],
            "host_page_protection_enforced": False,
            "normal_host_shell_or_title_executed": False,
        },
        "event_handle_wait": {
            "direct_call_site_count": 4,
            "create_call_sites": [
                {
                    "call_address": "0x84BE7088",
                    "return_address": "0x84BE708C",
                    "shape": (
                        "r3=r1+80 HANDLE*; r4=NULL or helper-built "
                        "X_OBJECT_ATTRIBUTES; r5=event type BOOL; "
                        "r6=low-byte initial state BOOL"
                    ),
                },
                {
                    "call_address": "0x84BE9A2C",
                    "return_address": "0x84BE9A30",
                    "shape": (
                        "r3=r1+124 HANDLE*; r4=NULL; r5=1 "
                        "EventSynchronizationObject; r6=0"
                    ),
                },
            ],
            "close_call_sites": [
                {
                    "call_address": "0x84BE9A8C",
                    "return_address": "0x84BE9A90",
                    "shape": "r3=BE handle loaded from r1+124",
                },
            ],
            "wait_call_sites": [
                {
                    "call_address": "0x84BF0E3C",
                    "return_address": "0x84BF0E40",
                    "shape": (
                        "r3=handle; r4=1; r5=alertable low byte; "
                        "r6=NULL or helper-produced BE s64 timeout"
                    ),
                },
            ],
            "all_frontier_calls_gated_by_exact_return_address": True,
            "handle_table": {
                "namespace_base": "0xF8000000",
                "first_handle": "0xF8000004",
                "capacity": 64,
                "stride": 4,
                "slot_zero_reserved": True,
                "pinned_xenia_provenance": (
                    "XObject::kHandleBase plus ObjectTable slot<<2"
                ),
                "disjoint_from_title_dispatch_and_import_ranges": True,
                "unknown_or_stale_handle_status": "0xC0000008",
            },
            "named_event_layout": {
                "object_attributes_size": 12,
                "root_directory": "0xFFFFFFFC",
                "attributes": "0x00000080 (case insensitive)",
                "name_descriptor": "big-endian 8-byte X_ANSI_STRING",
                "maximum_retained_name_bytes": 255,
                "duplicate_result": "0x40000000 (X_STATUS_OBJECT_NAME_EXISTS)",
                "duplicate_retains_same_handle": True,
            },
            "event_semantics": {
                "event_type_0": "notification/manual-reset",
                "event_type_1": "synchronization/auto-reset",
                "auto_reset_consumes_signal": True,
                "manual_reset_preserves_signal": True,
                "zero_timeout_unsignaled_result": "0x00000102",
                "invalid_handle_checked_before_timeout_pointer": True,
            },
            "wait_policy": {
                "host_thread_blocks": False,
                "null_or_negative_pending_wait": "scheduler_blocked",
                "zero_relative_timeout": "immediate X_STATUS_TIMEOUT",
                "positive_absolute_timeout": "unsupported_variant",
                "deadline_apc_and_signal_wakeup": "PORTME",
            },
            "transactional_policy": (
                "preflight the complete BE handle cell and optional name graph "
                "before table/refcount/output mutation; failed guest requests "
                "leave the output cell and table unchanged"
            ),
            "pinned_xenia_sources": [
                "src/xenia/kernel/util/object_table.cc",
                "src/xenia/kernel/xevent.cc",
                "src/xenia/kernel/xboxkrnl/xboxkrnl_ob.cc",
                "src/xenia/kernel/xboxkrnl/xboxkrnl_threading.cc",
                "src/xenia/xbox.h",
            ],
            "title_executed": False,
        },
        "message_box_ui": message_box_ui,
        "critical_sections": {
            "candidate_layout": {
                "0x00": "u8 type = 1 (SynchronizationEvent)",
                "0x01": "u8 absolute/spin = 0",
                "0x02": "u8 dispatcher header size = 4 dwords",
                "0x03": "u8 inserted = 0",
                "0x04": "be32 signal_state = 0",
                "0x08": "be32 wait_list_flink = critical_section + 8",
                "0x0C": "be32 wait_list_blink = critical_section + 8",
                "0x10": "be32 signed lock_count",
                "0x14": "be32 recursion_count",
                "0x18": "be32 owning guest PKTHREAD",
                "size": 28,
            },
            "layout_confidence": (
                "cross-reference-derived candidate; Xenon XDK/kernel confirmation "
                "is still required for dispatcher size and wait-list initialization"
            ),
            "layout_provenance": {
                "pinned_xenia": (
                    "confirms 28-byte total size, 16-byte dispatcher header, and "
                    "lock/recursion/owner offsets"
                ),
                "vendored_cxbx_original_xbox": (
                    "supports synchronization-event type, size byte, and self-linked "
                    "wait-list initialization; this is cross-generation evidence"
                ),
            },
            "frontier_call_sites": {
                "enter": [
                    "0x84B579CC", "0x84BDE26C", "0x84BEDADC", "0x84BEED8C",
                    "0x84BEF3A0", "0x84BF0C6C", "0x84BF0CF0"
                ],
                "initialize": [
                    "0x84B5796C", "0x84BDE614", "0x84BED954", "0x84D05740",
                    "0x84D05778", "0x84D057B0"
                ],
                "leave": [
                    "0x84B57A0C", "0x84BDE0C0", "0x84BDE20C", "0x84BEE164",
                    "0x84BEE2F4", "0x84BEEF18", "0x84BEEFB4", "0x84BEFB04",
                    "0x84BF0CA4", "0x84BF0D30",
                ],
            },
            "recursion_supported": True,
            "uncontended_transitions": [
                "free: lock=-1 recursion=0 owner=0",
                "first enter: lock=0 recursion=1 owner=current guest PKTHREAD",
                "recursive enter/leave update both counts",
                "final leave restores free state",
            ],
            "contention_policy": (
                "scheduler_blocked with no mutation; no host blocking or fake acquisition"
            ),
            "foreign_leave_policy": "guest_state with no mutation",
            "waiter_release_policy": (
                "scheduler_blocked with no mutation until park/wake queues exist"
            ),
            "tail_failure_provenance": {
                "call_address": "0x84BDE0C0",
                "inherited_return_address": "0x84BD7C9C",
                "runtime_records_exact_static_call_address": True,
            },
            "host_atomic_or_pthread_lock_used": False,
            "microsoft_contract": (
                "https://learn.microsoft.com/en-us/windows-hardware/drivers/"
                "debugger/displaying-a-critical-section"
            ),
        },
        "rtl_compare_memory_ulong": {
            "adapter_semantics": (
                "return leading matching bytes in multiples of four; stop at first "
                "mismatching big-endian guest ULONG"
            ),
            "all_seven_augmented_frontier_calls_ignore_result": True,
            "misaligned_source_or_length_result": 0,
            "microsoft_nt_documentation": (
                "https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/"
                "ntifs/nf-ntifs-rtlcomparememoryulong"
            ),
            "pinned_xenia_divergence": (
                "Xenia increments once per matching ULONG, scans after mismatches, and "
                "therefore does not return documented leading matching bytes"
            ),
            "vendored_cxbx_behavior": (
                "stops at the first mismatching ULONG and returns pointer byte distance"
            ),
        },
        "rtl_nt_status_to_dos_error": rtl_ntstatus_mapping,
        "thread_creation_required": {
            **thread_creation_boundary,
            "imports": thread_create_rows,
        },
        "fail_fast_frontier": unsupported_rows,
        "unresolved_indirect_runtime_surface": unresolved_indirect,
        "partial_portme": [
            {
                "name": "ExGetXConfigSetting",
                "portme": "// PORTME at 0x84D081EC: model additional XConfig variants explicitly.",
                "thunk_address": "0x84D081EC",
            },
            {
                "name": "NtAllocateVirtualMemory",
                "portme": "// PORTME at 0x84D0863C: recover non-frontier VM flags and protections.",
                "thunk_address": "0x84D0863C",
            },
            {
                "name": "NtFreeVirtualMemory",
                "portme": "// PORTME at 0x84D085EC: recover non-frontier free types and heap paths.",
                "thunk_address": "0x84D085EC",
            },
            {
                "name": "NtQueryVirtualMemory",
                "portme": "// PORTME at 0x84D086BC: query other guest heaps only with loader maps.",
                "thunk_address": "0x84D086BC",
            },
            {
                "name": "NtCreateEvent",
                "portme": "// PORTME at 0x84D0839C: retain longer/non-helper event-name forms.",
                "thunk_address": "0x84D0839C",
            },
            {
                "name": "NtClose",
                "portme": "// PORTME at 0x84D083AC: retain an event object across a concurrent final-handle close and wait.",
                "thunk_address": "0x84D083AC",
            },
            {
                "name": "NtWaitForSingleObjectEx",
                "portme": "// PORTME at 0x84D084EC: register scheduler deadlines, APCs, and event-signal wakeups.",
                "thunk_address": "0x84D084EC",
            },
            {
                "name": "RtlEnterCriticalSection",
                "portme": "// PORTME at 0x84D07FCC: park/wake a contending guest thread.",
                "thunk_address": "0x84D07FCC",
            },
            {
                "name": "RtlLeaveCriticalSection",
                "portme": "// PORTME at 0x84D07FDC: release and wake one queued guest waiter.",
                "thunk_address": "0x84D07FDC",
            },
            {
                "name": "RtlRaiseException",
                "portme": "// PORTME at 0x84D086CC: integrate guest exception dispatch/unwind.",
                "thunk_address": "0x84D086CC",
            },
            {
                "name": "RtlNtStatusToDosError",
                "portme": "// PORTME at 0x84D0864C: extend only for a licensed, pinned mapping and a proved caller status.",
                "thunk_address": "0x84D0864C",
            },
            {
                "name": "ExCreateThread",
                "portme": "// PORTME at 0x84D0876C: atomically own an X_KTHREAD-compatible object/handle, guarded stack, TLS/PCR/CPU context, runnable/exit state, close references, and teardown before completing the typed request.",
                "thunk_address": "0x84D0876C",
            },
            {
                "name": "XamShowMessageBoxUIEx",
                "portme": "// PORTME at 0x84D07EDC: name the opaque r10/result object only with exact UIEx ABI evidence; extend beyond the one-button APF shape only with another proved caller.",
                "thunk_address": "0x84D07EDC",
            },
        ],
        "terminal_outcomes": {
            "dispatch_status": "terminal_outcome",
            "guest_arguments_r3_through_r7_recorded_before_r3_is_cleared": True,
            "imports": terminal_rows,
            "ke_bug_check_tail_branch": {
                "call_address": "0x84BDAA24",
                "inherited_lr": True,
                "runtime_records_exact_static_call_address": True,
            },
            "resumable": False,
        },
        "exception_dispatch_required": {
            "dispatch_status": "exception_required",
            "imports": exception_rows,
            "exception_record_and_adapter_context_preserved": (
                "all 32 integer GPRs plus LR"
            ),
            "guest_thread_latched_until_seh_exists": True,
            "resumable_without_seh": False,
        },
        "test_contract": {
            "proves_big_endian_xconfig_value_and_size_writes": True,
            "proves_big_endian_ansi_string_layout": True,
            "proves_ansi_string_null_and_long_source_semantics": True,
            "proves_ansi_string_unterminated_source_is_transactional_fault": True,
            "proves_critical_section_candidate_28_byte_layout": True,
            "proves_critical_section_recursion": True,
            "proves_contention_and_foreign_leave_do_not_mutate": True,
            "proves_blocked_thread_retry_after_owner_release": True,
            "proves_duplicate_guest_thread_identity_is_rejected": True,
            "exhausts_all_tls_slots": True,
            "proves_cross_guest-thread_tls_isolation": True,
            "proves_32bit_result_sign_extension": True,
            "proves_rtl_leave_tail_failure_site_is_exact": True,
            "proves_explicit_configuration": True,
            "proves_no_generic_unsupported_frontier_imports": True,
            "proves_memory_oob_fault": True,
            "proves_rtl_result_is_bytes_not_ulong_count": True,
            "proves_terminal_outcomes_never_return_ok": True,
            "proves_ke_bug_check_tail_site_is_typed_terminal": True,
            "proves_exception_context_is_latched_until_seh_exists": True,
            "proves_exact_dbgprint_structured_event": True,
            "proves_dbgprint_rejects_other_call_shapes_and_bytes": True,
            "proves_retail_xex_default_heap_key_is_absent": True,
            "proves_retail_xex_pointer_is_validated_not_guessed": True,
            "proves_vm_loader_configuration_has_no_defaults": True,
            "proves_vm_core_ranges_are_disjoint": True,
            "proves_vm_other_mapping_exclusion": True,
            "proves_vm_64k_rounding_and_big_endian_outputs": True,
            "proves_vm_reserve_commit_decommit_release_query": True,
            "proves_vm_commit_zero_and_nozero": True,
            "proves_vm_recommit_preserves_first_page_backing": True,
            "proves_vm_failures_are_transactional": True,
            "proves_vm_ntstatus_sign_extension": True,
            "proves_vm_unproved_call_shapes_fail_closed": True,
            "proves_event_handle_namespace_and_capacity": True,
            "proves_event_handle_big_endian_transactional_output": True,
            "proves_named_event_reopen_and_reference_close": True,
            "proves_manual_and_auto_reset_event_semantics": True,
            "proves_zero_timeout_and_pending_scheduler_boundary": True,
            "proves_event_ntstatus_sign_extension": True,
            "proves_rtl_ntstatus_two_entry_mapping": True,
            "proves_rtl_ntstatus_unknown_status_fails_closed": True,
            "proves_rtl_ntstatus_exact_callsite_gate": True,
            "proves_rtl_ntstatus_input_and_result_extension": True,
            "proves_ui_exact_callsite_arguments_and_pointer_graph": True,
            "proves_ui_request_has_no_automatic_selection": True,
            "proves_ui_pending_overlapped_and_event_completion": True,
            "proves_ui_completion_failures_are_transactional": True,
            "proves_ui_requesting_thread_is_latched": True,
            "proves_thread_create_exact_frontier_shape": True,
            "proves_thread_create_other_direct_site_is_rejected": True,
            "proves_thread_create_request_is_transactional": True,
            "proves_thread_create_outputs_and_guest_entry_are_untouched": True,
            "proves_thread_create_requesting_thread_is_latched": True,
            "success_line": (
                "APF_BOOT_LEAF_ADAPTERS_PASS resumable_imports=24 "
                "terminal_imports=4 exception_imports=1 direct_sites=87 "
                "proved_indirect_import_sites=4 guest_threads=2 "
                "xconfig_writes=2 critical_sites=23 ansi_string_sites=2 "
                "be_compare_bytes=12 dbgprint_events=1 xex_absent=1 vm_sites=19 "
                "vm_pages=64 event_sites=4 event_capacity=64 "
                "ui_sites=1 ui_requests=1 thread_create_sites=1 "
                "thread_create_requests=1 unsupported_frontier_imports=0"
            ),
        },
        "limits": [
            "No generated APF translation unit is linked or executed.",
            "No guest PPCContext, stack, title scheduler, or exception model is started.",
            "The 30-import augmented frontier is path-insensitive and is not a successful boot-path trace.",
            "Five original and two second-wave indirect calls remain address-specific runtime-surface PORTMEs.",
            "ExCreateThread now publishes a non-resumable typed request; no completion exists until guest stack, object/handle, TLS/PCR/CPU state, and scheduler lifecycle ownership exist.",
            "TLS and critical-section guest-thread objects require a future scheduler-owned lifetime and detach discipline.",
            "Contended critical sections stop without mutation until scheduler park/wake queues exist.",
            "The 28-byte critical-section initialization is a cross-reference-derived candidate, not Xenon-hardware proof.",
            "The VM ledger does not yet apply host NOACCESS/read-only page protection; this bounded APF surface only proves READWRITE calls.",
            "Twenty-four imports resume or stop at an explicit scheduler/UI boundary, four produce terminal outcomes, one requires exception dispatch, one produces a non-resumable thread-create request, and no frontier import remains generically unsupported.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
