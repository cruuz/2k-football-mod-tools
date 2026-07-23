#!/usr/bin/env python3
"""Prove APF's immediate post-reserve boundary without executing title code.

The input checkpoint is the exact guarded NtAllocateVirtualMemory reserve
milestone: 264 guest instructions have run, the adapter returned success, and
the generated instruction at 0x84BED7BC has not run.  This analyzer verifies
that checkpoint and statically selects only the path through the next typed
boundary.  It does not invoke an adapter, _xstart, or any translated function.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "apf2k8_post_reserve_static/v1"
EXPECTED_DECODED_SIZE = 54_001_664
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)

EXPECTED_HASHES = {
    "retail_xex":
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
    "retail_volume":
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "guarded_second":
        "d60c0116a5445624453d867c8600c0466b06a0fb64f3bc183c7ebe730c651761",
    "second_static":
        "16f95dced67f975cbf4e4636a51d277c23d2ed1f5b7578d6b0704c27993802a0",
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
        "f8b91d4dc4d0d4eef4ea485984fb746f06c2e6df0b11d028ed6b9accfc30d664",
    "bridge_source":
        "f4f7cc44253bfacf6faf0520de28bd35d0c544928c1d9b415d7b9041fb4a9e1d",
    "ghidra_ledger":
        "447c7896020f48524ae71c93f02e6f7f2c9444188e4f97811a367a5dac8bf9dc",
}

TRACE = [
    0x84BED7BC, 0x84BED7C0, 0x84BED7C4, 0x84BED7C8,
    0x84BED7CC, 0x84BED7D0, 0x84BED7D8, 0x84BED7DC,
    0x84BED7E0, 0x84BED7E4, 0x84BED7E8, 0x84BED7EC,
    0x84BED7F0, 0x84BED7F4, 0x84BED7F8, 0x84BED7FC,
    0x84BED800, 0x84BED804, 0x84BED808,
]


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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def extract_generated_body(source_text: str, symbol: str) -> str:
    marker = f"PPC_FUNC_IMPL(__imp__{symbol}) {{"
    pattern = re.compile(
        re.escape(marker) + r"(.*?)(?=\n}\n\n__attribute__|\Z)", re.S)
    matches = pattern.findall(source_text)
    require(len(matches) == 1,
            f"generated body count changed for {symbol}")
    return marker + matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--decoded", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument(
        "--prior-report", type=Path,
        default=Path(
            "reports/static_recomp/"
            "apf2k8_guarded_second_boundary_execution.json"))
    parser.add_argument(
        "--generated-source", type=Path,
        default=Path(
            "build-static-recomp-apf/"
            "ppc-opcode-switch-budget-instrumented/ppc_recomp.217.cpp"))
    args = parser.parse_args()

    root = args.root.resolve()

    def resolve(path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    decoded = resolve(args.decoded)
    output = resolve(args.json)
    paths = {
        "retail_xex":
            root / "extracted/All-Pro Football 2K8 (USA)/default.xex",
        "retail_volume":
            root / "extracted/All-Pro Football 2K8 (USA)/0A",
        "guarded_second": resolve(args.prior_report),
        "second_static":
            root / "reports/static_recomp/apf2k8_second_boundary_static.json",
        "leaf_report":
            root / "reports/static_recomp/apf2k8_boot_leaf_adapters.json",
        "generated_source": resolve(args.generated_source),
        "opcode_sites":
            root / "reports/static_recomp/apf2k8_opcode_gap_sites.tsv",
        "switch_residue": root / (
            "reports/static_recomp/"
            "apf2k8_static_recomp_switch_tail_residue.tsv"),
        "xex_report": root / "reports/headers/apf2k8_xex_report.json",
        "leaf_source": root / "src/static_runtime/apf_boot_leaf_adapters.c",
        "guarded_harness":
            root / "tools/apf_guarded_second_boundary_execute.py",
        "bridge_source":
            root / "src/static_runtime/apf_first_entry_xenon_bridge.cpp",
        "ghidra_ledger": root / (
            "research/functions/apf2k8/ledger/"
            "apf2k8_functions_19456_19967.jsonl"),
    }
    required = [decoded, *paths.values()]
    require(all(path.is_file() and not path.is_symlink()
                for path in required),
            "post-reserve static input is missing or symlinked")

    verified_hashes: dict[str, str] = {}
    for name, path in paths.items():
        actual = sha256_file(path)
        require(actual == EXPECTED_HASHES[name],
                f"pinned input changed: {name}")
        verified_hashes[name] = actual
    require(decoded.stat().st_size == EXPECTED_DECODED_SIZE and
            sha256_file(decoded) == EXPECTED_DECODED_SHA256,
            "decoded APF image is not exact")

    prior = json.loads(paths["guarded_second"].read_text(encoding="utf-8"))
    execution = prior["generated_execution"]
    second = execution["second_boundary"]
    result = prior["result"]
    expected_vm_ledger = {
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
    }
    require(
        prior["schema"] ==
            "apf2k8_guarded_second_boundary_execution/v1" and
        execution["executed_guest_instruction_count"] == 264 and
        execution["last_executed_guest_pc"] == "0x84BED7B8" and
        execution["function_dispatch_count"] == 2 and
        second["import"] == "NtAllocateVirtualMemory" and
        second["call_pc"] == "0x84BED7B8" and
        second["return_pc"] == "0x84BED7BC" and
        second["thunk"] == "0x84D0863C" and
        second["adapter_status"] == "ok" and
        second["ntstatus_r3"] == "0x00000000" and
        second["base_value_after_be_u32"] == "0x40000000" and
        second["size_value_after_be_u32"] == "0x00100000" and
        second["generated_return_instruction_executed"] is False and
        result["second_typed_adapter_completed"] is True and
        result["continued_past_second_typed_boundary"] is False and
        prior["virtual_memory_ledger"] == expected_vm_ledger,
        "guarded reserve checkpoint changed")

    prior_pcs = execution["ordered_guest_pcs"]
    prior_trace_text = "".join(f"{pc}\n" for pc in prior_pcs).encode("ascii")
    require(len(prior_pcs) == 264 and
            prior_pcs[-1] == "0x84BED7B8" and
            sha256_bytes(prior_trace_text) ==
                execution["full_ordered_pc_sha256"] ==
                "b521057b939a97aee026b06f7fc667c1f6e463e160b32150b296e98cbe309cd0",
            "guarded reserve ordered trace changed")

    second_static = json.loads(
        paths["second_static"].read_text(encoding="utf-8"))
    require(
        second_static["schema"] == "apf2k8_second_boundary_static/v1" and
        second_static["descriptor_and_frames"]["allocator_stack"] ==
            "0x7001FC00" and
        second_static["static_trace"]
            ["cumulative_instruction_count_through_next_call"] == 264 and
        second_static["next_boundary"]["call_pc"] == "0x84BED7B8" and
        second_static["next_boundary"]["return_pc"] == "0x84BED7BC" and
        second_static["next_boundary"]["arguments"]
            ["size_value_be_u32"] == "0x00100000",
        "static reserve proof changed")

    generated_text = paths["generated_source"].read_text(encoding="utf-8")
    body = extract_generated_body(generated_text, "sub_84BED488")
    require("PPC_CALL_INDIRECT_FUNC" not in body,
            "indirect dispatch appeared in allocator owner")
    exact_fragments = [
        "ctx.lr = 0x84BED7BC;\n\t__imp__NtAllocateVirtualMemory(ctx, base);",
        "ctx.cr0.compare<int32_t>(ctx.r3.s32, 0, ctx.xer);",
        "if (ctx.cr0.lt) goto loc_84BED540;",
        "ctx.r11.u64 = PPC_LOAD_U32(ctx.r31.u32 + 316);",
        "if (!ctx.cr6.eq) goto loc_84BED7D8;",
        "PPC_STORE_U32(ctx.r31.u32 + 84, ctx.r10.u32);",
        "ctx.r28.u64 = ctx.r10.u64;",
        "if (!ctx.cr6.eq) goto loc_84BED844;",
        "ctx.r5.u64 = ctx.r5.u64 | 4096;",
        "ctx.r4.s64 = ctx.r31.s64 + 316;",
        "ctx.r3.s64 = ctx.r31.s64 + 84;",
        "ctx.lr = 0x84BED80C;\n\t__imp__NtAllocateVirtualMemory(ctx, base);",
    ]
    require(all(fragment in body for fragment in exact_fragments),
            "generated post-reserve sequence changed")
    require(len(TRACE) == 19 and len(set(TRACE)) == 19 and
            TRACE[0] == 0x84BED7BC and TRACE[-1] == 0x84BED808 and
            0x84BED7D4 not in TRACE and 0x84BED80C not in TRACE,
            "post-reserve trace shape changed")
    previous_position = -1
    for pc in TRACE:
        hook = f"VC_APF_GUEST_INSTRUCTION_STEP(0x{pc:08X}u);"
        require(body.count(hook) == 1,
                f"trace PC hook count changed: 0x{pc:08X}")
        position = body.index(hook)
        require(position > previous_position,
                f"trace PC order changed: 0x{pc:08X}")
        previous_position = position

    # The prior dynamic path plus the pinned generated operations reconstruct
    # the commit-size cell: r6=0x1000 is rounded at 0x84BED660..668 to 0x10000.
    required_prior_rounding_pcs = [
        "0x84BED654", "0x84BED658", "0x84BED65C", "0x84BED660",
        "0x84BED664", "0x84BED668", "0x84BED66C",
    ]
    require(all(pc in prior_pcs for pc in required_prior_rounding_pcs) and
            "ctx.r11.u64 = ctx.r6.u64 + ctx.r27.u64;" in body and
            "PPC_STORE_U32(ctx.r31.u32 + 316, ctx.r11.u32);" in body,
            "commit-size cell reconstruction changed")

    opcode_sites: set[int] = set()
    with paths["opcode_sites"].open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, dialect="excel-tab"):
            opcode_sites.add(int(row["address"], 16))
    switch_sites: set[int] = set()
    with paths["switch_residue"].open(
            encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, dialect="excel-tab"):
            switch_sites.add(int(row["target"], 16))
            switch_sites.update(
                int(value, 16)
                for value in row["switch_bctr_bases"].split(",") if value)
    trace_set = set(TRACE)
    opcode_intersection = sorted(trace_set & opcode_sites)
    switch_intersection = sorted(trace_set & switch_sites)
    require(not opcode_intersection,
            "opcode candidate entered post-reserve trace")
    require(not switch_intersection,
            "switch-tail residue entered post-reserve trace")

    xex_report = json.loads(paths["xex_report"].read_text(encoding="utf-8"))
    imports = [item for item in xex_report["imports"]["items"]
               if item["name"] == "NtAllocateVirtualMemory"]
    require(imports == [{
        "library": "xboxkrnl.exe",
        "library_version": "2.0.5759.0",
        "reference_address": "0x820006E8",
        "thunk_address": "0x84D0863C",
        "raw_word": "0x000100CC",
        "hint": 1,
        "ordinal": 204,
        "name": "NtAllocateVirtualMemory",
    }], "NtAllocateVirtualMemory import identity changed")

    leaf = json.loads(paths["leaf_report"].read_text(encoding="utf-8"))
    commit_rows = [
        site for site in leaf["virtual_memory"]["allocate_call_sites"]
        if site["call_address"] == "0x84BED808"
    ]
    require(len(commit_rows) == 1 and
            commit_rows[0]["caller"] == "sub_84BED488" and
            commit_rows[0]["return_address"] == "0x84BED80C" and
            commit_rows[0]["operation"] == "commit" and
            commit_rows[0]["allocation_types"] == ["0x60001000"] and
            commit_rows[0]["protect"] ==
                "0x00000004 (X_PAGE_READWRITE)" and
            commit_rows[0]["debug_memory"] == 0,
            "typed commit adapter evidence changed")
    leaf_source = paths["leaf_source"].read_text(encoding="utf-8")
    require("case 0x84BED80Cu:" in leaf_source and
            "vc_apf_nt_allocate_virtual_memory" in leaf_source and
            "reserve_site ? VC_APF_X_MEM_RESERVE" in leaf_source,
            "exact commit-site adapter support disappeared")

    ledger_rows = [
        json.loads(line)
        for line in paths["ghidra_ledger"].read_text(
            encoding="utf-8").splitlines()
    ]
    owner = [row for row in ledger_rows if row["address"] == "0x84BED488"]
    require(len(owner) == 1 and owner[0]["callees"] == ["0x84BD6DCC"] and
            "0x84BF1850" in owner[0]["callers"],
            "Ghidra allocator ownership changed")

    guarded_harness = paths["guarded_harness"].read_text(encoding="utf-8")
    bridge_source = paths["bridge_source"].read_text(encoding="utf-8")
    require(
        "/* Throw unconditionally: 0x84BED7BC must not execute "
        "in this milestone. */" in guarded_harness and
        "adapter_context.lr != 0x84BED7BCu" in guarded_harness and
        "0x84BED80Cu" not in guarded_harness and
        "[[noreturn]] void dispatch_and_stop" in bridge_source and
        "throw vc_apf_first_entry_boundary_stop" in bridge_source,
        "continuation authorization evidence changed")

    trace_text = "".join(f"0x{pc:08X}\n" for pc in TRACE).encode("ascii")

    def pin(name: str) -> dict[str, Any]:
        path = paths[name]
        return {
            "path": relative(path, root),
            "size": path.stat().st_size,
            "sha256": verified_hashes[name],
        }

    report: dict[str, Any] = {
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
            "pc": "0x84BED7BC",
            "lr": "0x84BED7BC",
            "r1": "0x7001FC00",
            "r31": "0x7001FC00",
            "r3_ntstatus": "0x00000000",
            "prior_executed_guest_instructions": 264,
            "last_executed_guest_pc": "0x84BED7B8",
            "generated_instruction_at_start_executed": False,
            "source": "proved guarded reserve-adapter terminal state",
            "big_endian_cells": {
                "0x7001FC50_reserved_base": "0x40000000",
                "0x7001FD34_reserved_size": "0x00100000",
                "0x7001FD3C_rounded_commit_size": "0x00010000",
            },
            "virtual_memory_ledger": expected_vm_ledger,
        },
        "branch_proof": [
            {
                "pc": "0x84BED7C0",
                "condition": "signed r3 (NTSTATUS) < 0",
                "known_input": "r3 = 0x00000000",
                "outcome": "not taken; reserve succeeded",
            },
            {
                "pc": "0x84BED7D0",
                "condition": "BE32[r31 + 316] != 0",
                "known_input": "BE32[0x7001FD3C] = 0x00010000",
                "outcome": "taken -> 0x84BED7D8; 0x84BED7D4 skipped",
            },
            {
                "pc": "0x84BED7EC",
                "condition": "copied base != r28",
                "known_input": "0x40000000 == 0x40000000",
                "outcome": "not taken; prepare commit import",
            },
        ],
        "static_trace": {
            "continuation_instruction_count_through_next_call": len(TRACE),
            "cumulative_instruction_count_through_next_call": 264 + len(TRACE),
            "unique_pc_count": len(set(TRACE)),
            "first_pc": f"0x{TRACE[0]:08X}",
            "last_pc": f"0x{TRACE[-1]:08X}",
            "ordered_guest_pcs": [f"0x{pc:08X}" for pc in TRACE],
            "ordered_pc_sha256": sha256_bytes(trace_text),
            "owner": "sub_84BED488",
            "generated_source": relative(paths["generated_source"], root),
            "unresolved_indirect_before_boundary": False,
            "opcode_candidate_intersection_count": len(opcode_intersection),
            "switch_tail_residue_intersection_count": len(switch_intersection),
        },
        "next_boundary": {
            "classification": "typed_import",
            "library": "xboxkrnl.exe",
            "library_version": "2.0.5759.0",
            "name": "NtAllocateVirtualMemory",
            "operation": "commit",
            "ordinal": 204,
            "thunk": "0x84D0863C",
            "call_pc": "0x84BED808",
            "return_pc": "0x84BED80C",
            "arguments": {
                "r3_base_pointer": "0x7001FC54",
                "base_value_be_u32": "0x40000000",
                "r4_size_pointer": "0x7001FD3C",
                "size_value_be_u32": "0x00010000",
                "r5_allocation_type": "0x60001000",
                "r6_protection": "0x00000004",
                "r7_debug_memory": "0x00000000",
            },
            "typed_leaf_adapter_exact_site_supported": True,
            "adapter_invoked_by_this_analysis": False,
        },
        "authorization": {
            "typed_adapter_site_is_execution_authority": False,
            "existing_guarded_harness_authorizes_return_at_0x84BED7BC": False,
            "continuation_executed_by_this_analysis": False,
            "commit_executed_by_this_analysis": False,
            "generated_return_0x84BED80C_executed": False,
            "stop_reason": (
                "the prior isolated gate throws unconditionally after the "
                "reserve adapter; no exact continuation token/stage/PC/LR/"
                "state gate authorizes 0x84BED7BC"
            ),
        },
        "ordered_prerequisites": [
            {
                "order": 1,
                "requirement": (
                    "Create an isolated third-boundary gate with a new token "
                    "and require stage=post-reserve, PC/LR=0x84BED7BC, "
                    "264 prior instructions, and the exact reserve VM ledger."
                ),
            },
            {
                "order": 2,
                "requirement": (
                    "Before continuation, verify BE32 cells 0x7001FC50="
                    "0x40000000, 0x7001FD34=0x00100000, and "
                    "0x7001FD3C=0x00010000 while preserving guest memory and "
                    "both execution budgets."
                ),
            },
            {
                "order": 3,
                "requirement": (
                    "Authorize only the exact commit ABI at 0x84BED808, then "
                    "validate r3, both BE output cells, allocation slot 0, the "
                    "first page's commit state, the remaining 15 reserved "
                    "pages, and backing-memory zeroing before 0x84BED80C."
                ),
            },
        ],
        "portme": [
            "// PORTME at 0x84BED7BC: add an exact token+stage+PC/LR+post-reserve-VM-ledger continuation gate before executing this generated instruction.",
            "// PORTME at 0x84BED808: dispatch only the proved NtAllocateVirtualMemory commit ABI and stop in the bridge after the adapter returns.",
            "// PORTME at 0x84BED80C: verify commit status, BE pointer writes, page-state transition, and zeroed backing bytes before executing the generated return instruction.",
        ],
        "inputs": {
            "retail_xex": pin("retail_xex"),
            "retail_volume": pin("retail_volume"),
            "decoded_image": {
                "size": decoded.stat().st_size,
                "sha256": EXPECTED_DECODED_SHA256,
                "temporary_validator_artifact": True,
                "preserved_by_analyzer": True,
            },
            "guarded_second_boundary_report": pin("guarded_second"),
            "second_boundary_static_report": pin("second_static"),
            "typed_leaf_adapter_report": pin("leaf_report"),
            "generated_owner_source": pin("generated_source"),
            "opcode_gap_sites": pin("opcode_sites"),
            "switch_tail_residue": pin("switch_residue"),
            "xex_import_report": pin("xex_report"),
            "typed_leaf_adapter_source": pin("leaf_source"),
            "guarded_second_boundary_harness": pin("guarded_harness"),
            "permanent_boundary_stop_bridge": pin("bridge_source"),
            "ghidra_owner_ledger": pin("ghidra_ledger"),
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(
        "APF_POST_RESERVE_STATIC_REPORT start=0x84BED7BC prior=264 "
        "next=NtAllocateVirtualMemory operation=commit call=0x84BED808 "
        "return=0x84BED80C continuation=19 cumulative=283 "
        "indirect=0 opcode=0 switch=0 executed=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AnalysisError as error:
        raise SystemExit(f"apf_post_reserve_static: {error}")
