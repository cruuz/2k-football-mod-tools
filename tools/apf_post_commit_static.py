#!/usr/bin/env python3
"""Prove APF's immediate post-commit path without executing title code."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "apf2k8_post_commit_static/v1"
EXPECTED_DECODED_SIZE = 54_001_664
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_HASHES = {
    "retail_xex":
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
    "retail_volume":
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "guarded_third":
        "cf16bb85f8065812d3987216abcfae45aee775e758354e152294f5cfb4708c17",
    "post_reserve_static":
        "1a0b9ac08bc17007a7d7922024d6703eab702fb900bf60d08bbc84fda566cc2c",
    "leaf_report":
        "6b7b7d65bb5d0cc5d90bc7dd4abb34b8b3a780a9e3be7e57afb1946a260f0b5e",
    "generated_source":
        "ed97b7cf74b5368eeae914b770108681e0447bb7afa75238604b2e684234d5e3",
    "opcode_sites":
        "29ba6fc510492cfa58d63b28b5cea606455841b3d3fbe14fd70b883e78e7903b",
    "switch_residue":
        "42698f9dc3d5a03079a4e8dd6e0fc55060a87eabc2f3176a92c15156a31dbcb0",
    "xex_report":
        "dfd21f9db2fdb683b2dbd0390d351fdac84ba1e796a0e0c5e0e60c28827f3f1c",
    "leaf_source":
        "4e162c5b45e78665a63428033fc4b564740fb3753f222515028aa00c16829a10",
    "guarded_harness":
        "7bdb109dbfc535f2c3dd869e17656e7b6541b97bce91202e6374962d099f9467",
    "bridge_source":
        "f4f7cc44253bfacf6faf0520de28bd35d0c544928c1d9b415d7b9041fb4a9e1d",
    "ghidra_ledger":
        "447c7896020f48524ae71c93f02e6f7f2c9444188e4f97811a367a5dac8bf9dc",
}

TRACE = [
    0x84BED80C, 0x84BED810, 0x84BED838, 0x84BED83C,
    0x84BED840, 0x84BED844, 0x84BED848, 0x84BED84C,
    0x84BED850, 0x84BED854,
]
for _ in range(8):
    TRACE.extend([
        0x84BED858, 0x84BED85C, 0x84BED860, 0x84BED864,
        0x84BED868,
    ])
TRACE.extend([
    0x84BED86C, 0x84BED870, 0x84BED874, 0x84BED878,
    0x84BED87C,
])
TRACE.extend(range(0x84BED8A0, 0x84BED90C, 4))


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
        "guarded_third": root / (
            "reports/static_recomp/"
            "apf2k8_guarded_third_boundary_execution.json"),
        "post_reserve_static": root / (
            "reports/static_recomp/apf2k8_post_reserve_static.json"),
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
        "xex_report": root / "reports/headers/apf2k8_xex_report.json",
        "leaf_source": root / "src/static_runtime/apf_boot_leaf_adapters.c",
        "guarded_harness":
            root / "tools/apf_guarded_third_boundary_execute.py",
        "bridge_source":
            root / "src/static_runtime/apf_first_entry_xenon_bridge.cpp",
        "ghidra_ledger": root / (
            "research/functions/apf2k8/ledger/"
            "apf2k8_functions_19456_19967.jsonl"),
    }
    require(decoded.is_file() and not decoded.is_symlink(),
            "decoded image missing or symlinked")
    require(all(path.is_file() and not path.is_symlink()
                for path in paths.values()),
            "post-commit static input missing or symlinked")
    for name, path in paths.items():
        require(sha256_file(path) == EXPECTED_HASHES[name],
                f"pinned input changed: {name}")
    require(decoded.stat().st_size == EXPECTED_DECODED_SIZE and
            sha256_file(decoded) == EXPECTED_DECODED_SHA256,
            "decoded APF image changed")

    prior = json.loads(paths["guarded_third"].read_text(encoding="utf-8"))
    execution = prior["generated_execution"]
    third = execution["third_boundary"]
    ledger = prior["virtual_memory_ledger"]
    require(
        prior["schema"] ==
            "apf2k8_guarded_third_boundary_execution/v1" and
        prior["result"]["child_outcome"] == "expected_third_boundary" and
        prior["result"]["third_typed_adapter_completed"] is True and
        prior["result"]["continued_past_third_typed_boundary"] is False and
        execution["executed_guest_instruction_count"] == 283 and
        execution["function_dispatch_count"] == 3 and
        execution["last_executed_guest_pc"] == "0x84BED808" and
        third["call_pc"] == "0x84BED808" and
        third["return_pc"] == "0x84BED80C" and
        third["thunk"] == "0x84D0863C" and
        third["ntstatus_r3"] == "0x00000000" and
        third["generated_return_instruction_executed"] is False and
        ledger["committed_page_count"] == 1 and
        ledger["remaining_reserved_page_count"] == 15 and
        ledger["first_page_backing_zeroed"] is True and
        ledger["remaining_allocation_backing_pattern_exact"] is True and
        ledger["backing_fnv1a64_after"] == "0x8179632E8A902325",
        "guarded commit checkpoint changed")

    decoded_bytes = decoded.read_bytes()
    global_flags_address = 0x852D6484
    image_base = 0x82000000
    global_offset = global_flags_address - image_base
    global_flags = int.from_bytes(
        decoded_bytes[global_offset:global_offset + 4], "big")
    require(global_flags == 0, "retail process-global flag cell changed")

    source = paths["generated_source"].read_text(encoding="utf-8")
    body = extract_generated_body(source)
    require("PPC_CALL_INDIRECT_FUNC" not in body,
            "indirect dispatch appeared in allocator owner")
    fragments = [
        "ctx.lr = 0x84BED80C;\n\t__imp__NtAllocateVirtualMemory(ctx, base);",
        "if (!ctx.cr0.lt) goto loc_84BED838;",
        "ctx.r8.s64 = 8;",
        "PPC_STORE_U32(ctx.r10.u32 + 0, ctx.r11.u32);",
        "if (!ctx.cr0.eq) goto loc_84BED858;",
        "ctx.r10.u64 = PPC_LOAD_U32(ctx.r23.u32 + 25732);",
        "if (ctx.cr0.eq) goto loc_84BED8A0;",
        "PPC_STORE_U16(ctx.r8.u32 + 0, ctx.r9.u16);",
        "PPC_STORE_U8(ctx.r9.u32 + 5, ctx.r8.u8);",
        "PPC_STORE_U32(ctx.r9.u32 + 16, ctx.r11.u32);",
        "PPC_STORE_U16(ctx.r11.u32 + 368, ctx.r27.u16);",
        "PPC_STORE_U16(ctx.r11.u32 + 58, ctx.r10.u16);",
        "ctx.lr = 0x84BED90C;\n\t__imp__KeGetCurrentProcessType(ctx, base);",
    ]
    require(all(fragment in body for fragment in fragments),
            "generated post-commit semantics changed")
    require(len(TRACE) == 82 and len(set(TRACE)) == 47 and
            TRACE[0] == 0x84BED80C and TRACE[-1] == 0x84BED908 and
            0x84BED814 not in TRACE and 0x84BED880 not in TRACE and
            0x84BED90C not in TRACE,
            "post-commit trace shape changed")
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
            "unsupported generated residue intersects post-commit trace")

    leaf = json.loads(paths["leaf_report"].read_text(encoding="utf-8"))
    process_rows = [item for item in leaf["guest_abi"]["implemented_imports"]
                    if item["name"] == "KeGetCurrentProcessType"]
    require(len(process_rows) == 1 and
            process_rows[0]["thunk_address"] == "0x84D0868C" and
            any(site["call_address"] == "0x84BED908" and
                site["return_address"] == "0x84BED90C"
                for site in process_rows[0]["calls"]),
            "typed process-type adapter evidence changed")
    leaf_source = paths["leaf_source"].read_text(encoding="utf-8")
    require(
        "case VC_APF_THUNK_KE_GET_CURRENT_PROCESS_TYPE:" in leaf_source and
        "vc_apf_set_r3(context, runtime->config.process_type);" in
            leaf_source,
        "typed process-type implementation changed")

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
            "source": "proved guarded commit-adapter terminal state",
            "pc": "0x84BED80C",
            "lr": "0x84BED80C",
            "r1": "0x7001FC00",
            "r31": "0x7001FC00",
            "r3_ntstatus": "0x00000000",
            "prior_executed_guest_instructions": 283,
            "last_executed_guest_pc": "0x84BED808",
            "generated_instruction_at_start_executed": False,
            "virtual_memory_ledger": ledger,
            "known_registers": {
                "r21": "0xFFFFFFFF",
                "r22": "0x00000000",
                "r23": "0x852D0000",
                "r24": "0x00000002",
                "r27": "0x0000FFFF",
                "r28": "0x40000000",
                "r29": "0x000005AC",
            },
            "retail_global_flags": {
                "address": "0x852D6484",
                "be_u32": "0x00000000",
                "bit_0x00000800": False,
            },
        },
        "branch_proof": [
            {
                "pc": "0x84BED810",
                "condition": "signed r3 (NTSTATUS) >= 0",
                "known_input": "r3 = 0x00000000",
                "outcome": "taken -> 0x84BED838",
            },
            {
                "pc": "0x84BED868",
                "condition": "decremented r8 != 0",
                "known_input": "r8 initialized to 8",
                "outcome": "eight exact iterations of 0x84BED858..0x84BED868",
            },
            {
                "pc": "0x84BED87C",
                "condition": "BE32[0x852D6484] & 0x00000800 == 0",
                "known_input": "retail BE32 cell = 0x00000000",
                "outcome": "taken -> 0x84BED8A0; 0x84BED880..0x84BED89C skipped",
            },
        ],
        "static_trace": {
            "owner": "sub_84BED488",
            "first_pc": "0x84BED80C",
            "last_pc": "0x84BED908",
            "continuation_instruction_count_through_next_call": len(TRACE),
            "cumulative_instruction_count_through_next_call": 283 + len(TRACE),
            "unique_pc_count": len(set(TRACE)),
            "ordered_pc_sha256": trace_sha256(TRACE),
            "ordered_guest_pcs": [f"0x{pc:08X}" for pc in TRACE],
            "unresolved_indirect_before_boundary": False,
            "opcode_candidate_intersection_count": len(opcode_hits),
            "switch_tail_residue_intersection_count": len(residue_hits),
            "generated_source": relative(paths["generated_source"], root),
        },
        "deterministic_page_initialization": {
            "committed_page_base": "0x40000000",
            "committed_page_size": "0x00010000",
            "list_iteration_count": 8,
            "list_first_pointer": "0x40000590",
            "list_terminal_address": "0x40000600",
            "descriptor_size_units_16_bytes": 99,
            "descriptor_flags": "0xEEFFEEFF",
            "descriptor_input_flags": "0x00000002",
            "descriptor_tail_offset": "0x00000610",
            "nonzero_byte_count": 34,
            "page_sha256_before_process_type_call":
                "f0072c49de8cb307781499a69e189990e2b0837652d8afb232227f1a18da5d85",
            "allocation_fnv1a64_before_process_type_call":
                "0x233B6EC7DF8372AE",
            "remaining_15_page_pattern_preserved": True,
        },
        "next_boundary": {
            "name": "KeGetCurrentProcessType",
            "library": "xboxkrnl.exe",
            "ordinal": 102,
            "classification": "typed_import",
            "call_pc": "0x84BED908",
            "return_pc": "0x84BED90C",
            "thunk": "0x84D0868C",
            "arguments": {},
            "configured_result_r3": "0x00000001",
            "typed_leaf_adapter_exact_site_supported": True,
            "adapter_invoked_by_this_analysis": False,
        },
        "authorization": {
            "continuation_executed_by_this_analysis": False,
            "process_type_adapter_executed_by_this_analysis": False,
            "generated_return_0x84BED90C_executed": False,
            "typed_adapter_site_is_execution_authority": False,
            "stop_reason": (
                "the prior isolated gate throws after the commit adapter; "
                "no post-commit token/stage/PC/LR/state gate yet authorizes "
                "0x84BED80C"
            ),
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
            "// PORTME at 0x84BED80C: add a new exact post-commit token+stage+PC/LR+VM/backing/global-state gate before executing this instruction.",
            "// PORTME at 0x84BED908: dispatch only the proved KeGetCurrentProcessType site and stop after its typed adapter returns.",
            "// PORTME at 0x84BED90C: verify r3=1 and the initialized committed-page bytes before executing the generated return instruction.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(
        "APF_POST_COMMIT_STATIC_REPORT start=0x84BED80C prior=283 "
        "next=KeGetCurrentProcessType call=0x84BED908 return=0x84BED90C "
        "continuation=82 cumulative=365 indirect=0 opcode=0 switch=0 "
        "executed=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
