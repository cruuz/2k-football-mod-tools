#!/usr/bin/env python3
"""Prove APF's immediate post-process-type path without executing title code."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "apf2k8_post_process_type_static/v1"
EXPECTED_DECODED_SIZE = 54_001_664
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_HASHES = {
    "retail_xex":
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
    "retail_volume":
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "guarded_fourth":
        "98403d883c3e20c69e2655482f67353ff30f68e24bd1815e7366de731c529b08",
    "leaf_report":
        "6b7b7d65bb5d0cc5d90bc7dd4abb34b8b3a780a9e3be7e57afb1946a260f0b5e",
    "generated_source":
        "ed97b7cf74b5368eeae914b770108681e0447bb7afa75238604b2e684234d5e3",
    "opcode_sites":
        "29ba6fc510492cfa58d63b28b5cea606455841b3d3fbe14fd70b883e78e7903b",
    "switch_residue":
        "42698f9dc3d5a03079a4e8dd6e0fc55060a87eabc2f3176a92c15156a31dbcb0",
    "leaf_source":
        "4e162c5b45e78665a63428033fc4b564740fb3753f222515028aa00c16829a10",
    "guarded_harness":
        "7a4af9c78ce600695f9f83b9904083e9cdeab024692aab30d244c9ff4c85c4c3",
}

TRACE = [
    0x84BED90C, 0x84BED910, 0x84BED914, 0x84BED918, 0x84BED91C,
]
for _ in range(128):
    TRACE.extend([
        0x84BED920, 0x84BED924, 0x84BED928, 0x84BED92C, 0x84BED930,
    ])
TRACE.extend([
    0x84BED934, 0x84BED938, 0x84BED93C, 0x84BED940, 0x84BED944,
    0x84BED948, 0x84BED94C, 0x84BED950, 0x84BED954,
])


class AnalysisError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AnalysisError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def trace_sha256(trace: list[int]) -> str:
    return hashlib.sha256("".join(
        f"0x{pc:08X}\n" for pc in trace).encode("ascii")).hexdigest()


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def pin(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": relative(path, root),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def extract_generated_body(source: str) -> str:
    marker = "PPC_FUNC_IMPL(__imp__sub_84BED488) {"
    pattern = re.compile(
        re.escape(marker) + r"(.*?)(?=\n}\n\n__attribute__|\Z)", re.S)
    matches = pattern.findall(source)
    require(len(matches) == 1, "allocator owner body count changed")
    return marker + matches[0]


def build_expected_page() -> bytes:
    page = bytearray(0x10000)
    base = 0x40000000

    def store16(offset: int, value: int) -> None:
        page[offset:offset + 2] = value.to_bytes(2, "big")

    def store32(offset: int, value: int) -> None:
        page[offset:offset + 4] = value.to_bytes(4, "big")

    store16(0, 0x0063)
    page[5] = 1
    store32(16, 0xEEFFEEFF)
    store32(20, 2)
    store16(58, 0x0610)
    store32(76, base + 0x590)
    store16(368, 0xFFFF)
    for index in range(7):
        offset = 0x590 + index * 0x10
        store32(offset, base + offset + 0x10)
    page[379] = 1
    for index in range(128):
        offset = 384 + index * 8
        store32(offset, base + offset)
        store32(offset + 4, base + offset)
    store32(88, base + 88)
    store32(92, base + 88)
    return bytes(page)


def allocation_fnv(page: bytes) -> int:
    value = 14695981039346656037
    for byte in page:
        value = ((value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    for index in range(0x10000, 0x100000):
        byte = (index * 131 + 17) & 0xFF
        value = ((value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--decoded", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    resolve = lambda path: path.resolve() if path.is_absolute() else \
        (root / path).resolve()
    decoded = resolve(args.decoded)
    output = resolve(args.json)
    paths = {
        "retail_xex":
            root / "extracted/All-Pro Football 2K8 (USA)/default.xex",
        "retail_volume": root / "extracted/All-Pro Football 2K8 (USA)/0A",
        "guarded_fourth": root / (
            "reports/static_recomp/"
            "apf2k8_guarded_fourth_boundary_execution.json"),
        "leaf_report":
            root / "reports/static_recomp/apf2k8_boot_leaf_adapters.json",
        "generated_source": root / (
            "build-static-recomp-apf/ppc-opcode-switch-budget-instrumented/"
            "ppc_recomp.217.cpp"),
        "opcode_sites":
            root / "reports/static_recomp/apf2k8_opcode_gap_sites.tsv",
        "switch_residue": root / (
            "reports/static_recomp/"
            "apf2k8_static_recomp_switch_tail_residue.tsv"),
        "leaf_source": root / "src/static_runtime/apf_boot_leaf_adapters.c",
        "guarded_harness":
            root / "tools/apf_guarded_fourth_boundary_execute.py",
    }
    require(decoded.is_file() and not decoded.is_symlink(),
            "decoded image missing or symlinked")
    require(all(path.is_file() and not path.is_symlink()
                for path in paths.values()),
            "post-process-type static input missing or symlinked")
    for name, path in paths.items():
        require(sha256_file(path) == EXPECTED_HASHES[name],
                f"pinned input changed: {name}")
    require(decoded.stat().st_size == EXPECTED_DECODED_SIZE and
            sha256_file(decoded) == EXPECTED_DECODED_SHA256,
            "decoded APF image changed")

    prior = json.loads(paths["guarded_fourth"].read_text(encoding="utf-8"))
    execution = prior["generated_execution"]
    fourth = execution["fourth_boundary"]
    memory = prior["virtual_memory_and_initialization"]
    require(
        prior["schema"] == "apf2k8_guarded_fourth_boundary_execution/v1" and
        prior["result"]["child_outcome"] == "expected_fourth_boundary" and
        prior["result"]["fourth_typed_adapter_completed"] is True and
        prior["result"]["continued_past_fourth_typed_boundary"] is False and
        execution["executed_guest_instruction_count"] == 365 and
        execution["function_dispatch_count"] == 4 and
        execution["last_executed_guest_pc"] == "0x84BED908" and
        fourth["return_pc"] == "0x84BED90C" and
        fourth["r3_process_type_result"] == "0x00000001" and
        fourth["generated_return_instruction_executed"] is False and
        memory["vm_ledger_exact"] is True and
        memory["initialized_committed_page_exact"] is True and
        memory["remaining_15_page_pattern_exact"] is True,
        "guarded process-type checkpoint changed")

    source = paths["generated_source"].read_text(encoding="utf-8")
    body = extract_generated_body(source)
    require("PPC_CALL_INDIRECT_FUNC" not in body,
            "indirect dispatch appeared in allocator owner")
    fragments = [
        "VC_APF_GUEST_INSTRUCTION_STEP(0x84BED90Cu);",
        "PPC_STORE_U8(ctx.r9.u32 + 379, ctx.r3.u8);",
        "ctx.r10.s64 = 128;",
        "PPC_STORE_U32(ctx.r11.u32 + 0, ctx.r11.u32);",
        "PPC_STORE_U32(ctx.r11.u32 + 4, ctx.r11.u32);",
        "if (!ctx.cr0.eq) goto loc_84BED920;",
        "ctx.cr6.compare<int32_t>(ctx.r21.s32, -1, ctx.xer);",
        "if (!ctx.cr6.eq) goto loc_84BED958;",
        "ctx.r3.u64 = ctx.r29.u64;",
        "ctx.r21.u64 = ctx.r29.u64;",
        "ctx.lr = 0x84BED958;\n\t__imp__RtlInitializeCriticalSection(ctx, base);",
    ]
    require(all(fragment in body for fragment in fragments),
            "generated post-process-type semantics changed")
    require(len(TRACE) == 654 and len(set(TRACE)) == 19 and
            TRACE[0] == 0x84BED90C and TRACE[-1] == 0x84BED954 and
            TRACE.count(0x84BED920) == 128 and
            0x84BED958 not in TRACE,
            "post-process-type trace shape changed")
    for pc in set(TRACE):
        require(body.count(
            f"VC_APF_GUEST_INSTRUCTION_STEP(0x{pc:08X}u);") == 1,
            f"generated hook count changed: 0x{pc:08X}")

    opcode_sites: set[int] = set()
    with paths["opcode_sites"].open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            opcode_sites.add(int(row["address"], 16))
    residue_text = paths["switch_residue"].read_text(encoding="utf-8")
    opcode_hits = sorted(set(TRACE) & opcode_sites)
    residue_hits = [pc for pc in sorted(set(TRACE))
                    if f"0x{pc:08X}" in residue_text]
    require(not opcode_hits and not residue_hits,
            "unsupported generated residue intersects continuation")

    page = build_expected_page()
    page_sha = hashlib.sha256(page).hexdigest()
    page_nonzero = sum(byte != 0 for byte in page)
    page_fnv = allocation_fnv(page)
    require(page_sha ==
            "8174339c35c7a8d0f68fcce0ed9c10697dad9fe6a7a0237e0d6738a35edfda07" and
            page_nonzero == 799 and page_fnv == 0xF663B4BBF571B2AD,
            "deterministic page model changed")

    leaf = json.loads(paths["leaf_report"].read_text(encoding="utf-8"))
    rows = [item for item in leaf["guest_abi"]["implemented_imports"]
            if item["name"] == "RtlInitializeCriticalSection"]
    require(len(rows) == 1 and rows[0]["thunk_address"] == "0x84D07FBC" and
            any(site["call_address"] == "0x84BED954" and
                site["return_address"] == "0x84BED958"
                for site in rows[0]["calls"]),
            "typed critical-section adapter evidence changed")
    leaf_source = paths["leaf_source"].read_text(encoding="utf-8")
    require(
        "case VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION:" in leaf_source and
        "memset(bytes, 0, VC_APF_RTL_CRITICAL_SECTION_SIZE);" in leaf_source and
        "vc_apf_store_be_u32(bytes + 16u, UINT32_MAX);" in leaf_source,
        "typed critical-section implementation changed")

    report = {
        "schema": SCHEMA,
        "scope": {
            "method": "nonexecuting path-specific static continuation",
            "translated_title_functions_called": False,
            "leaf_adapter_invoked": False,
            "subprocess_invoked": False,
            "native_boot_proved": False,
            "main_menu_proved": False,
        },
        "start_checkpoint": {
            "source": "proved guarded process-type-adapter terminal state",
            "pc": "0x84BED90C",
            "lr": "0x84BED90C",
            "r3_process_type": "0x00000001",
            "prior_executed_guest_instructions": 365,
            "last_executed_guest_pc": "0x84BED908",
            "generated_instruction_at_start_executed": False,
            "known_registers": {
                "r21": "0xFFFFFFFF",
                "r29": "0x40000610",
                "r31": "0x7001FC00",
            },
        },
        "branch_proof": [
            {
                "pc": "0x84BED930",
                "condition": "decremented r10 != 0",
                "known_input": "r10 initialized to 128",
                "outcome": "128 exact iterations of 0x84BED920..0x84BED930",
            },
            {
                "pc": "0x84BED948",
                "condition": "r21 != -1",
                "known_input": "r21 = 0xFFFFFFFF",
                "outcome": "not taken; execute 0x84BED94C..0x84BED954",
            },
        ],
        "static_trace": {
            "owner": "sub_84BED488",
            "first_pc": "0x84BED90C",
            "last_pc": "0x84BED954",
            "continuation_instruction_count_through_next_call": len(TRACE),
            "cumulative_instruction_count_through_next_call": 365 + len(TRACE),
            "unique_pc_count": len(set(TRACE)),
            "ordered_pc_sha256": trace_sha256(TRACE),
            "ordered_guest_pcs": [f"0x{pc:08X}" for pc in TRACE],
            "unresolved_indirect_before_boundary": False,
            "opcode_candidate_intersection_count": len(opcode_hits),
            "switch_tail_residue_intersection_count": len(residue_hits),
            "generated_source": relative(paths["generated_source"], root),
        },
        "deterministic_page_before_boundary": {
            "committed_page_base": "0x40000000",
            "process_type_byte_address": "0x4000017B",
            "process_type_byte": "0x01",
            "allocator_list_head_count": 128,
            "allocator_list_first_address": "0x40000180",
            "allocator_list_last_address": "0x40000578",
            "secondary_list_head_address": "0x40000058",
            "critical_section_address": "0x40000610",
            "nonzero_byte_count": page_nonzero,
            "page_sha256": page_sha,
            "allocation_fnv1a64": f"0x{page_fnv:016X}",
            "remaining_15_page_pattern_preserved": True,
        },
        "next_boundary": {
            "name": "RtlInitializeCriticalSection",
            "library": "xboxkrnl.exe",
            "ordinal": 302,
            "classification": "typed_import",
            "call_pc": "0x84BED954",
            "return_pc": "0x84BED958",
            "thunk": "0x84D07FBC",
            "arguments": {"r3_critical_section": "0x40000610"},
            "result": "void",
            "typed_leaf_adapter_exact_site_supported": True,
            "adapter_invoked_by_this_analysis": False,
        },
        "authorization": {
            "continuation_executed_by_this_analysis": False,
            "critical_section_adapter_executed_by_this_analysis": False,
            "generated_return_0x84BED958_executed": False,
            "typed_adapter_site_is_execution_authority": False,
        },
        "inputs": {
            **{name: pin(path, root) for name, path in paths.items()},
            "decoded_image": {
                "size": decoded.stat().st_size,
                "sha256": sha256_file(decoded),
                "temporary_validator_artifact": True,
                "preserved_by_analyzer": True,
            },
        },
        "portme": [
            "// PORTME at 0x84BED90C: add an exact post-process-type token+stage+PC/LR/page-state gate before executing this instruction.",
            "// PORTME at 0x84BED954: dispatch only the proved RtlInitializeCriticalSection site and stop after its typed adapter returns.",
            "// PORTME at 0x84BED958: verify the exact initialized critical-section bytes before executing the generated return instruction.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(
        "APF_POST_PROCESS_TYPE_STATIC_REPORT start=0x84BED90C prior=365 "
        "next=RtlInitializeCriticalSection call=0x84BED954 "
        "return=0x84BED958 continuation=654 cumulative=1019 indirect=0 "
        "opcode=0 switch=0 executed=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
