#!/usr/bin/env python3
"""Prove APF's path after the fifth guarded boundary without executing it."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "apf2k8_post_critical_section_static/v1"
EXPECTED_DECODED_SIZE = 54_001_664
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_HASHES = {
    "retail_xex":
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
    "retail_volume":
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "guarded_fifth":
        "d12897cd8c5575c1f770a7f5429f02777c1028574014fb7e59def40dade9478d",
    "guarded_fifth_driver":
        "254e71ccd95b2f1140129b2edc5961d3be25afb1cda6b256ad1e988993e149d0",
    "leaf_report":
        "6b7b7d65bb5d0cc5d90bc7dd4abb34b8b3a780a9e3be7e57afb1946a260f0b5e",
    "leaf_source":
        "4e162c5b45e78665a63428033fc4b564740fb3753f222515028aa00c16829a10",
    "allocator_source":
        "ed97b7cf74b5368eeae914b770108681e0447bb7afa75238604b2e684234d5e3",
    "entry_source":
        "c4c107f141c223995362e71750574bf3a416807ed768fa391cc8bd32252d552d",
    "save_source":
        "d753c3a5820a218fa29868ae941a5af9e759332ce772362cab64ec75ede1f251",
    "opcode_sites":
        "29ba6fc510492cfa58d63b28b5cea606455841b3d3fbe14fd70b883e78e7903b",
    "switch_residue":
        "42698f9dc3d5a03079a4e8dd6e0fc55060a87eabc2f3176a92c15156a31dbcb0",
}


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


def rr(first: int, last: int) -> list[int]:
    require(first <= last and (last - first) % 4 == 0,
            "invalid static trace interval")
    return list(range(first, last + 1, 4))


def exact_trace() -> list[int]:
    trace: list[int] = []
    # sub_84BED488 publishes its per-heap critical section and enters the
    # internal range builder.
    trace += rr(0x84BED958, 0x84BED980)
    trace += [0x84BECD78, 0x84BECD7C]
    trace += rr(0x84BD6DD0, 0x84BD6DFC)
    trace += rr(0x84BECD80, 0x84BECDB8)
    trace += [0x84BECDBC, 0x84BECDC0]
    trace += rr(0x84BECDC8, 0x84BECDDC)
    # The 64-KiB committed frontier already covers the new block, so no VM
    # import is required.  Build the first free-range descriptors instead.
    trace += rr(0x84BECE30, 0x84BECE90)
    trace += [0x84BEBC38, 0x84BEBC3C]
    trace += rr(0x84BD6DE8, 0x84BD6DFC)
    trace += rr(0x84BEBC40, 0x84BEBC5C)
    trace += [0x84BEBCDC, 0x84BEBCE0]
    trace += rr(0x84BEBA50, 0x84BEBA78)
    trace += rr(0x84BEBBEC, 0x84BEBC0C)
    trace += rr(0x84BEBCE4, 0x84BEBD20)
    trace += rr(0x84BD6E38, 0x84BD6E50)
    trace += rr(0x84BECE94, 0x84BECED0)
    trace += [0x84BEC448, 0x84BEC44C]
    trace += rr(0x84BD6DEC, 0x84BD6DFC)
    trace += rr(0x84BEC450, 0x84BEC478)
    trace += [0x84BEC564, 0x84BEC568, 0x84BEC47C, 0x84BEC480]
    trace += rr(0x84BEC4A0, 0x84BEC4C8)
    trace += [0x84BEC50C, 0x84BEC510, 0x84BEC514]
    trace += rr(0x84BEC528, 0x84BEC568)
    trace += [0x84BEC56C, 0x84BEC570, 0x84BEC578]
    trace += rr(0x84BD6E3C, 0x84BD6E50)
    trace += [0x84BECED4, 0x84BECED8, 0x84BECEDC]
    trace += rr(0x84BD6E20, 0x84BD6E50)
    # Finish sub_84BED488 and unwind into the startup owner.
    trace += rr(0x84BED984, 0x84BEDA1C)
    trace += rr(0x84BD6E1C, 0x84BD6E50)
    trace += rr(0x84BF18F8, 0x84BF1920)
    trace += [0x84BF1960, 0x84BF1964]
    trace += rr(0x84BF1998, 0x84BF19A4)
    trace += [0x84BE9D3C, 0x84BE9D40]
    # sub_84BF0C50 reaches the first global critical-section enter.
    trace += [0x84BF0C50, 0x84BF0C54]
    trace += rr(0x84BD6DE8, 0x84BD6DFC)
    trace += rr(0x84BF0C58, 0x84BF0C6C)
    return trace


def extract_generated_body(source: str, symbol: str) -> str:
    marker = f"PPC_FUNC_IMPL(__imp__{symbol}) {{"
    pattern = re.compile(
        re.escape(marker) + r"(.*?)(?=\n}\n\n__attribute__|\Z)", re.S)
    matches = pattern.findall(source)
    require(len(matches) == 1, f"generated body count changed: {symbol}")
    return marker + matches[0]


def trace_sha256(trace: list[int]) -> str:
    return hashlib.sha256("".join(
        f"0x{pc:08X}\n" for pc in trace).encode("ascii")).hexdigest()


def build_page() -> bytes:
    page = bytearray(0x10000)
    base = 0x40000000

    def store16(offset: int, value: int) -> None:
        page[offset:offset + 2] = value.to_bytes(2, "big")

    def store32(offset: int, value: int) -> None:
        page[offset:offset + 4] = value.to_bytes(4, "big")

    # State proved before the fifth call.
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

    # Exact 28-byte RtlInitializeCriticalSection result.
    store32(0x610, 0x01000400)
    store32(0x614, 0)
    store32(0x618, base + 0x618)
    store32(0x61C, base + 0x618)
    store32(0x620, 0xFFFFFFFF)
    store32(0x624, 0)
    store32(0x628, 0)

    # 0x84BED968 publishes that critical-section pointer in the heap header.
    store32(0x580, base + 0x610)
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
        "guarded_fifth": root / (
            "reports/static_recomp/"
            "apf2k8_guarded_fifth_boundary_execution.json"),
        "guarded_fifth_driver":
            root / "tools/apf_guarded_fifth_boundary_execute.py",
        "leaf_report":
            root / "reports/static_recomp/apf2k8_boot_leaf_adapters.json",
        "leaf_source": root / "src/static_runtime/apf_boot_leaf_adapters.c",
        "allocator_source": root / (
            "build-static-recomp-apf/ppc-opcode-switch-budget-instrumented/"
            "ppc_recomp.217.cpp"),
        "entry_source": root / (
            "build-static-recomp-apf/ppc-opcode-switch-budget-instrumented/"
            "ppc_recomp.216.cpp"),
        "save_source": root / (
            "build-static-recomp-apf/ppc-opcode-switch-budget-instrumented/"
            "ppc_recomp.212.cpp"),
        "opcode_sites":
            root / "reports/static_recomp/apf2k8_opcode_gap_sites.tsv",
        "switch_residue": root / (
            "reports/static_recomp/"
            "apf2k8_static_recomp_switch_tail_residue.tsv"),
    }
    require(decoded.is_file() and not decoded.is_symlink(),
            "decoded image missing or symlinked")
    require(all(path.is_file() and not path.is_symlink()
                for path in paths.values()),
            "post-critical-section static input missing or symlinked")
    for name, path in paths.items():
        require(sha256_file(path) == EXPECTED_HASHES[name],
                f"pinned input changed: {name}")
    require(decoded.stat().st_size == EXPECTED_DECODED_SIZE and
            sha256_file(decoded) == EXPECTED_DECODED_SHA256,
            "decoded APF image changed")

    prior = json.loads(paths["guarded_fifth"].read_text(encoding="utf-8"))
    execution = prior["generated_execution"]
    fifth = execution["fifth_boundary"]
    memory = prior["virtual_memory_and_initialization"]
    require(
        prior["schema"] == "apf2k8_guarded_fifth_boundary_execution/v1" and
        prior["result"]["child_outcome"] == "expected_fifth_boundary" and
        prior["result"]["fifth_typed_adapter_completed"] is True and
        prior["result"]["continued_past_fifth_typed_boundary"] is False and
        execution["executed_guest_instruction_count"] == 1019 and
        execution["function_dispatch_count"] == 5 and
        execution["last_executed_guest_pc"] == "0x84BED954" and
        fifth["return_pc"] == "0x84BED958" and
        fifth["critical_section_initialized_exact"] is True and
        fifth["generated_return_instruction_executed"] is False and
        memory["vm_ledger_exact"] is True and
        memory["committed_page_count"] == 1 and
        memory["remaining_reserved_page_count"] == 15 and
        memory["post_adapter_page_sha256"] ==
            "87438b39f9268a5dd7e49711573bd66cab9b0bb378579b0ddd962b884506f1f3",
        "guarded fifth checkpoint changed")

    allocator_source = paths["allocator_source"].read_text(encoding="utf-8")
    entry_source = paths["entry_source"].read_text(encoding="utf-8")
    save_source = paths["save_source"].read_text(encoding="utf-8")
    bodies = {
        "sub_84BED488": extract_generated_body(
            allocator_source, "sub_84BED488"),
        "sub_84BECD78": extract_generated_body(
            allocator_source, "sub_84BECD78"),
        "sub_84BEBC38": extract_generated_body(
            allocator_source, "sub_84BEBC38"),
        "sub_84BEBA50": extract_generated_body(
            allocator_source, "sub_84BEBA50"),
        "sub_84BEC448": extract_generated_body(
            allocator_source, "sub_84BEC448"),
        "sub_84BF1850": extract_generated_body(
            allocator_source, "sub_84BF1850"),
        "sub_84BF1950": extract_generated_body(
            allocator_source, "sub_84BF1950"),
        "sub_84BF0C50": extract_generated_body(
            allocator_source, "sub_84BF0C50"),
        "__savegprlr_22": extract_generated_body(
            save_source, "__savegprlr_22"),
    }
    require(all("PPC_CALL_INDIRECT_FUNC" not in body
                for name, body in bodies.items()
                if name not in {"sub_84BF1950", "sub_84BF0C50"}) and
            bodies["sub_84BF1950"].count("PPC_CALL_INDIRECT_FUNC") == 1 and
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BF198Cu);" in
                bodies["sub_84BF1950"] and
            bodies["sub_84BF0C50"].count("PPC_CALL_INDIRECT_FUNC") == 1 and
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BF0C94u);" in
                bodies["sub_84BF0C50"],
            "indirect-dispatch placement changed around the sixth boundary")
    fragments = {
        "sub_84BED488": [
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BED958u);",
            "PPC_STORE_U32(ctx.r11.u32 + 1408, ctx.r21.u32);",
            "ctx.r9.u64 = ctx.r7.u64 + ctx.r11.u64;",
            "ctx.r4.u64 = ctx.r30.u64 + ctx.r3.u64;",
            "ctx.lr = 0x84BED984;\n\tsub_84BECD78(ctx, base);",
        ],
        "sub_84BECD78": [
            "ctx.lr = 0x84BECD80;\n\t__savegprlr_22(ctx, base);",
            "if (!ctx.cr6.eq) goto loc_84BECDC4;",
            "if (ctx.cr6.lt) goto loc_84BECE30;",
            "ctx.lr = 0x84BECE94;\n\tsub_84BEBC38(ctx, base);",
            "ctx.lr = 0x84BECED4;\n\tsub_84BEC448(ctx, base);",
        ],
        "sub_84BEBC38": [
            "ctx.lr = 0x84BEBCE4;\n\tsub_84BEBA50(ctx, base);",
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BEBD20u);",
        ],
        "sub_84BEBA50": [
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BEBA50u);",
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BEBC0Cu);",
        ],
        "sub_84BEC448": [
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BEC448u);",
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BEC578u);",
        ],
        "sub_84BF1850": [
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BF18F8u);",
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BF1920u);",
        ],
        "sub_84BF1950": [
            "ctx.lr = 0x84BF1960;\n\tsub_84BF1850(ctx, base);",
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BF19A4u);",
        ],
        "sub_84BF0C50": [
            "ctx.r3.u64 = ctx.r28.u64;",
            "ctx.lr = 0x84BF0C70;\n\t__imp__RtlEnterCriticalSection(ctx, base);",
        ],
        "__savegprlr_22": [
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BD6DD0u);",
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BD6DFCu);",
        ],
    }
    for symbol, required_fragments in fragments.items():
        require(all(fragment in bodies[symbol]
                    for fragment in required_fragments),
                f"generated continuation changed: {symbol}")

    trace = exact_trace()
    require(len(trace) == 314 and len(set(trace)) == 269 and
            trace[0] == 0x84BED958 and trace[-1] == 0x84BF0C6C and
            0x84BF0C70 not in trace,
            "post-critical-section trace shape changed")
    all_bodies = allocator_source + "\n" + save_source + "\n" + entry_source
    for pc in trace:
        require(all_bodies.count(
            f"VC_APF_GUEST_INSTRUCTION_STEP(0x{pc:08X}u);") >= 1,
            f"generated hook missing: 0x{pc:08X}")

    opcode_sites: set[int] = set()
    with paths["opcode_sites"].open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            opcode_sites.add(int(row["address"], 16))
    residue_text = paths["switch_residue"].read_text(encoding="utf-8")
    opcode_hits = sorted(set(trace) & opcode_sites)
    residue_hits = [pc for pc in trace
                    if f"0x{pc:08X}" in residue_text]
    require(not opcode_hits and not residue_hits,
            "unsupported generated residue intersects continuation")

    page = build_page()
    page_sha = hashlib.sha256(page).hexdigest()
    page_nonzero = sum(byte != 0 for byte in page)
    page_fnv = allocation_fnv(page)
    require(page_sha ==
            "d3123ade0ce122f0daab9b571be7d07de8f6e1e700ed4a575a34614d776cbaf9" and
            page_nonzero == 814 and page_fnv == 0xA2F6E3132B6EE02A,
            "deterministic pre-sixth page model changed")

    image = decoded.read_bytes()
    critical_offset = 0x84F02424 - 0x82000000
    critical_bytes = image[critical_offset:critical_offset + 28]
    require(len(critical_bytes) == 28 and
            critical_bytes.hex() ==
                "010004000000000084f0242c84f0242cffffffff0000000000000000" and
            hashlib.sha256(critical_bytes).hexdigest() ==
                "8f2d30b7ed222954eca71ef8530a158f7a9c2f711341572943c56f2f18454422",
            "retail global critical-section bytes changed")

    leaf = json.loads(paths["leaf_report"].read_text(encoding="utf-8"))
    rows = [item for item in leaf["guest_abi"]["implemented_imports"]
            if item["name"] == "RtlEnterCriticalSection"]
    require(len(rows) == 1 and rows[0]["thunk_address"] == "0x84D07FCC" and
            any(site["call_address"] == "0x84BF0C6C" and
                site["return_address"] == "0x84BF0C70"
                for site in rows[0]["calls"]),
            "typed critical-section-enter call-site evidence changed")
    critical = leaf["critical_sections"]
    require(critical["candidate_layout"]["size"] == 28 and
            "0x84BF0C6C" in critical["frontier_call_sites"]["enter"] and
            critical["uncontended_transitions"][1].startswith(
                "first enter: lock=0 recursion=1"),
            "typed critical-section semantics changed")
    leaf_source = paths["leaf_source"].read_text(encoding="utf-8")
    for fragment in (
        "case VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION:",
        "vc_apf_store_be_u32(view.bytes + 16u, 0u);",
        "vc_apf_store_be_u32(view.bytes + 20u, 1u);",
        "vc_apf_store_be_u32(view.bytes + 24u, current_thread);",
    ):
        require(fragment in leaf_source,
                "typed critical-section adapter semantics changed")

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
            "source": "proved guarded critical-section-adapter terminal state",
            "pc": "0x84BED958",
            "lr": "0x84BED958",
            "prior_executed_guest_instructions": 1019,
            "prior_function_dispatches": 5,
            "last_executed_guest_pc": "0x84BED954",
            "generated_instruction_at_start_executed": False,
            "known_registers": {
                "r21": "0x40000610",
                "r26": "0x00000000",
                "r28": "0x40010000",
                "r29": "0x40000610",
                "r30": "0x00000630",
                "r31": "0x7001FC00",
            },
        },
        "branch_proof": [
            {
                "pc": "0x84BECDB8",
                "condition": "r28 != r29",
                "known_values": "r28=r29=0x40000000",
                "outcome": "not taken; read BE16[0x40000000]=0x0063",
            },
            {
                "pc": "0x84BECDDC",
                "condition": "r30+16 < r8",
                "known_values": "0x40000690 < 0x40010000 is true",
                "outcome": "taken to in-range descriptor construction at 0x84BECE30",
            },
            {
                "pc": "0x84BED988",
                "condition": "range-builder result r3 == 0",
                "known_values": "sub_84BECD78 returns r3=1 on the selected path",
                "outcome": "not taken; finish the allocator object and unwind",
            },
            {
                "pc": "0x84BF0C6C",
                "condition": "next external dependency",
                "known_values": "r3=0x84F02424, exact free retail critical section",
                "outcome": "stop before typed RtlEnterCriticalSection dispatch",
            },
        ],
        "static_trace": {
            "owners": [
                "sub_84BED488", "sub_84BECD78", "sub_84BEBC38",
                "sub_84BEBA50", "sub_84BEC448", "sub_84BF1850",
                "sub_84BF1950", "sub_84BF0C50", "_xstart",
                "save/restore GPR helpers",
            ],
            "first_pc": "0x84BED958",
            "last_pc": "0x84BF0C6C",
            "continuation_instruction_count_through_next_call": len(trace),
            "cumulative_instruction_count_through_next_call": 1019 + len(trace),
            "unique_pc_count": len(set(trace)),
            "ordered_pc_sha256": trace_sha256(trace),
            "ordered_guest_pcs": [f"0x{pc:08X}" for pc in trace],
            "unresolved_indirect_before_boundary": False,
            "opcode_candidate_intersection_count": len(opcode_hits),
            "switch_tail_residue_intersection_count": len(residue_hits),
            "generated_sources": [
                relative(paths["allocator_source"], root),
                relative(paths["save_source"], root),
                relative(paths["entry_source"], root),
            ],
        },
        "deterministic_state_before_boundary": {
            "vm_ledger": {
                "active_allocation_count": 1,
                "allocation_base": "0x40000000",
                "allocation_size": "0x00100000",
                "committed_pages": [0],
                "reserved_pages": list(range(1, 16)),
            },
            "published_pointer_checkpoint": {
                "critical_section_address": "0x40000610",
                "critical_section_exact": True,
                "published_critical_section_pointer_address": "0x40000580",
                "published_critical_section_pointer": "0x40000610",
                "nonzero_byte_count": page_nonzero,
                "sha256": page_sha,
            },
            "allocation_fnv1a64_after_pointer_publish":
                f"0x{page_fnv:016X}",
            "allocation_fnv1a64_at_next_boundary": "0x182C7A2CE1705280",
            "remaining_15_page_pattern_preserved": True,
            "global_critical_section": {
                "address": "0x84F02424",
                "size": 28,
                "sha256": hashlib.sha256(critical_bytes).hexdigest(),
                "dispatcher_header": "0x01000400",
                "wait_list_flink": "0x84F0242C",
                "wait_list_blink": "0x84F0242C",
                "lock_count": -1,
                "recursion_count": 0,
                "owning_thread": "0x00000000",
            },
        },
        "next_boundary": {
            "name": "RtlEnterCriticalSection",
            "library": "xboxkrnl.exe",
            "ordinal": 293,
            "classification": "typed_import",
            "operation": "uncontended first enter of retail global lock",
            "call_pc": "0x84BF0C6C",
            "return_pc": "0x84BF0C70",
            "thunk": "0x84D07FCC",
            "arguments": {
                "r3_critical_section": "0x84F02424",
            },
            "configured_current_guest_thread": "0x70020200",
            "expected_transition": {
                "lock_count": 0,
                "recursion_count": 1,
                "owning_thread": "0x70020200",
            },
            "typed_leaf_adapter_exact_site_supported": True,
            "adapter_invoked_by_this_analysis": False,
        },
        "authorization": {
            "continuation_executed_by_this_analysis": False,
            "critical_section_adapter_executed_by_this_analysis": False,
            "generated_return_0x84BF0C70_executed": False,
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
            "// PORTME at 0x84BED958: require an exact fifth-stage token+PC/LR+register+VM/backing gate before executing this instruction.",
            "// PORTME at 0x84BF0C6C: dispatch only the proved RtlEnterCriticalSection ABI and stop after its typed adapter returns.",
            "// PORTME at 0x84BF0C70: verify the exact lock/recursion/owner transition before executing the generated return instruction.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(
        "APF_POST_CRITICAL_SECTION_STATIC_REPORT start=0x84BED958 "
        "prior=1019 next=RtlEnterCriticalSection operation=uncontended_enter "
        "call=0x84BF0C6C return=0x84BF0C70 continuation=314 "
        "cumulative=1333 indirect=0 opcode=0 switch=0 executed=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
