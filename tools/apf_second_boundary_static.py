#!/usr/bin/env python3
"""Prove APF's next first-entry boundary without executing title code.

This is deliberately a path-specific static analyzer.  It starts from the
already observed guarded-entry return state (PC 0x84BF188C, r3 == 0), checks
the generated instruction corpus, decoded retail image, Ghidra ledger, import
table, and typed leaf-adapter report, and emits only the next mechanically
proved boundary.  It never links or calls _xstart or another translated title
function.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "apf2k8_second_boundary_static/v1"
IMAGE_BASE = 0x82000000
EXPECTED_DECODED_SIZE = 54_001_664
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_VOLUME_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)
EXPECTED_GUARDED_REPORT_SHA256 = (
    "81a3f676a5985290a89a83aaf14543893bf0d97888b88764a24ccb337687cbca"
)


class AnalysisError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AnalysisError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def pin(path: Path, root: Path, include_sha: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": relative(path, root),
        "size": path.stat().st_size,
    }
    if include_sha:
        result["sha256"] = sha256_file(path)
    return result


def rr(first: int, last: int) -> list[int]:
    require(first <= last and (last - first) % 4 == 0,
            "invalid static trace interval")
    return list(range(first, last + 1, 4))


def exact_continuation_trace() -> list[int]:
    """Return the statically selected PPC PCs through the next import call."""
    trace: list[int] = []

    # sub_84BF1850: r3 == NULL takes the descriptor/allocation path.
    trace += [0x84BF188C, 0x84BF1890]
    trace += rr(0x84BF18A8, 0x84BF18B4)
    trace += rr(0x84BF18B8, 0x84BF18C0) * 6
    trace += rr(0x84BF18C4, 0x84BF18F4)

    # sub_84BED488 prologue and __savegprlr_21.
    trace += [0x84BED488, 0x84BED48C]
    trace += rr(0x84BD6DCC, 0x84BD6DFC)
    trace += rr(0x84BED490, 0x84BED4D0)
    trace += rr(0x84BED4D4, 0x84BED4DC) * 6
    trace += rr(0x84BED4E0, 0x84BED508)

    # 48-byte, nonoverlapping descriptor copy.  Destination and source are
    # both 8-byte aligned, so the forward-copy helper takes its six-u64 path.
    trace += rr(0x84BD8410, 0x84BD841C)
    trace += rr(0x84BD6E60, 0x84BD6E74)
    trace += rr(0x84BD6EC4, 0x84BD6EDC)
    trace += rr(0x84BD6EE0, 0x84BD6F00)
    trace += rr(0x84BD6F04, 0x84BD6F0C) * 6
    trace += [0x84BD6F10, 0x84BD6F14, 0x84BD6F34, 0x84BD6F38]

    # Default fields, 64-KiB rounding, and reserve call preparation.
    trace += rr(0x84BED50C, 0x84BED51C)
    trace += [0x84BED538, 0x84BED53C, 0x84BED548, 0x84BED54C,
              0x84BED550, 0x84BED554, 0x84BED558]
    trace += rr(0x84BED560, 0x84BED5E0)
    trace += rr(0x84BED5F0, 0x84BED600)
    trace += rr(0x84BED654, 0x84BED66C)
    trace += rr(0x84BED62C, 0x84BED648)
    trace += rr(0x84BED680, 0x84BED688)
    trace += rr(0x84BED690, 0x84BED698)
    trace += rr(0x84BED798, 0x84BED7B8)
    return trace


def extract_generated_body(corpus: Path, symbol: str) -> tuple[Path, str]:
    marker = f"PPC_FUNC_IMPL(__imp__{symbol}) {{"
    matches: list[tuple[Path, str]] = []
    pattern = re.compile(
        re.escape(marker) + r"(.*?)(?=\n}\n\n__attribute__|\Z)", re.S)
    for source in sorted(corpus.glob("ppc_recomp.*.cpp")):
        text = source.read_text(encoding="utf-8", errors="strict")
        found = pattern.search(text)
        if found:
            matches.append((source, found.group(0)))
    require(len(matches) == 1, f"generated body count changed for {symbol}")
    return matches[0]


def load_be_u32(image: bytes, address: int) -> int:
    offset = address - IMAGE_BASE
    require(0 <= offset <= len(image) - 4,
            f"decoded address is out of bounds: 0x{address:08X}")
    return int.from_bytes(image[offset:offset + 4], "big")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--decoded", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=Path(
        "build-static-recomp-apf/ppc-opcode-switch-budget-instrumented"))
    args = parser.parse_args()

    root = args.root.resolve()
    resolve = lambda path: path.resolve() if path.is_absolute() else \
        (root / path).resolve()
    decoded_path = resolve(args.decoded)
    output_path = resolve(args.json)
    corpus = resolve(args.corpus)
    xex = root / "extracted/All-Pro Football 2K8 (USA)/default.xex"
    volume = root / "extracted/All-Pro Football 2K8 (USA)/0A"
    guarded_path = root / "reports/static_recomp/apf2k8_guarded_first_entry_execution.json"
    composed_path = root / "reports/static_recomp/apf2k8_static_recomp_opcode_switch_composed.json"
    leaf_path = root / "reports/static_recomp/apf2k8_boot_leaf_adapters.json"
    xex_report_path = root / "reports/headers/apf2k8_xex_report.json"
    opcode_path = root / "reports/static_recomp/apf2k8_opcode_gap_sites.tsv"
    switch_path = root / "reports/static_recomp/apf2k8_static_recomp_switch_tail_residue.tsv"
    ledger_paths = [
        root / "research/functions/apf2k8/ledger/apf2k8_functions_19456_19967.jsonl",
        root / "research/functions/apf2k8/ledger/apf2k8_functions_19968_20479.jsonl",
    ]
    adapter_source = root / "src/static_runtime/apf_boot_leaf_adapters.c"

    required = [decoded_path, xex, volume, guarded_path, composed_path,
                leaf_path, xex_report_path, opcode_path, switch_path,
                *ledger_paths, adapter_source]
    require(all(path.is_file() and not path.is_symlink() for path in required),
            "static-continuation input is missing or symlinked")
    require(corpus.is_dir() and not corpus.is_symlink(),
            "instrumented corpus is missing or symlinked")
    require(sha256_file(xex) == EXPECTED_XEX_SHA256,
            "retail APF XEX hash changed")
    require(sha256_file(volume) == EXPECTED_VOLUME_SHA256,
            "retail APF volume hash changed")
    require(sha256_file(guarded_path) == EXPECTED_GUARDED_REPORT_SHA256,
            "guarded first-entry report changed")
    require(decoded_path.stat().st_size == EXPECTED_DECODED_SIZE and
            sha256_file(decoded_path) == EXPECTED_DECODED_SHA256,
            "decoded APF image is not exact")

    guarded = json.loads(guarded_path.read_text(encoding="utf-8"))
    execution = guarded["generated_execution"]
    result = guarded["result"]
    require(guarded["schema"] == "apf2k8_guarded_first_entry_execution/v2" and
            result["expected_first_typed_boundary_reached"] is True and
            result["continued_past_first_typed_boundary"] is False and
            execution["first_import_return"] == "0x84BF188C" and
            execution["adapter_return_value_r3"] == "0x00000000" and
            execution["executed_guest_instruction_count"] == 38,
            "guarded first-boundary state changed")

    image = decoded_path.read_bytes()
    expected_words = {
        0x852D64A0: 0x00000000,  # heap singleton before first construction
        0x852D6484: 0x00000000,  # allocator feature flags
        0x84F02404: 0x00100000,
        0x84F02408: 0x00020000,
        0x84F02410: 0x00010000,
        0x84F0240C: 0x00010000,
    }
    require(all(load_be_u32(image, address) == value
                for address, value in expected_words.items()),
            "retail initialized data changed on the continuation path")

    bodies: dict[str, str] = {}
    origins: dict[str, str] = {}
    for symbol in ("sub_84BF1850", "sub_84BED488", "sub_84BD8410",
                   "sub_84BD6E60", "__savegprlr_21"):
        origin, body = extract_generated_body(corpus, symbol)
        bodies[symbol] = body
        origins[symbol] = relative(origin, root)
        require("PPC_CALL_INDIRECT_FUNC" not in body,
                f"indirect dispatch entered continuation owner {symbol}")

    exact_fragments = {
        "sub_84BF1850": [
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BF188Cu);",
            "if (ctx.cr0.eq) goto loc_84BF18A8;",
            "ctx.lr = 0x84BF18F8;\n\tsub_84BED488(ctx, base);",
        ],
        "sub_84BED488": [
            "ctx.lr = 0x84BED490;\n\t__savegprlr_21(ctx, base);",
            "ctx.lr = 0x84BED50C;\n\tsub_84BD8410(ctx, base);",
            "ctx.r5.u64 = ctx.r5.u64 | 8192;",
            "ctx.lr = 0x84BED7BC;\n\t__imp__NtAllocateVirtualMemory(ctx, base);",
        ],
        "sub_84BD8410": [
            "if (!ctx.cr0.lt) goto loc_84BD8420;",
            "sub_84BD6E60(ctx, base);",
        ],
        "sub_84BD6E60": [
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BD6E60u);",
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BD6F38u);",
        ],
        "__savegprlr_21": [
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BD6DCCu);",
            "VC_APF_GUEST_INSTRUCTION_STEP(0x84BD6DFCu);",
        ],
    }
    for symbol, fragments in exact_fragments.items():
        require(all(fragment in bodies[symbol] for fragment in fragments),
                f"generated continuation sequence changed in {symbol}")

    trace = exact_continuation_trace()
    require(len(trace) == 226 and len(set(trace)) == 181 and
            trace[0] == 0x84BF188C and trace[-1] == 0x84BED7B8,
            "static continuation trace shape changed")
    all_generated = "\n".join(bodies.values())
    for pc in set(trace):
        require(f"VC_APF_GUEST_INSTRUCTION_STEP(0x{pc:08X}u);" in all_generated,
                f"trace PC lacks an instruction-budget hook: 0x{pc:08X}")

    opcode_sites: set[int] = set()
    with opcode_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, dialect="excel-tab"):
            opcode_sites.add(int(row["address"], 16))
    switch_sites: set[int] = set()
    with switch_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, dialect="excel-tab"):
            switch_sites.add(int(row["target"], 16))
            for value in row["switch_bctr_bases"].split(","):
                if value:
                    switch_sites.add(int(value, 16))
    require(set(trace).isdisjoint(opcode_sites),
            "opcode candidate entered exact continuation trace")
    require(set(trace).isdisjoint(switch_sites),
            "switch-tail residue entered exact continuation trace")

    composed = json.loads(composed_path.read_text(encoding="utf-8"))
    frontier = composed["first_entry_intersection"]
    require(frontier["opcode_candidate_sites_in_frontier"] == 0 and
            frontier["unresolved_switch_occurrences_in_frontier"] == 0,
            "composed first-entry candidate audit changed")

    xex_report = json.loads(xex_report_path.read_text(encoding="utf-8"))
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

    leaf = json.loads(leaf_path.read_text(encoding="utf-8"))
    reserve_sites = leaf["virtual_memory"]["allocate_call_sites"]
    reserve = [site for site in reserve_sites
               if site["call_address"] == "0x84BED7B8"]
    require(len(reserve) == 1 and reserve[0]["return_address"] == "0x84BED7BC" and
            reserve[0]["operation"] == "reserve" and
            reserve[0]["allocation_types"] == ["0x60002000"] and
            reserve[0]["protect"] == "0x00000004 (X_PAGE_READWRITE)" and
            reserve[0]["debug_memory"] == 0,
            "typed VM adapter evidence changed")
    adapter_text = adapter_source.read_text(encoding="utf-8")
    require("case 0x84BED7BCu:" in adapter_text and
            "vc_apf_nt_allocate_virtual_memory" in adapter_text,
            "exact reserve-site adapter implementation disappeared")

    # The Ghidra function ledger independently establishes the direct call
    # ownership used by the generated path.
    ledger_rows = [
        json.loads(line)
        for ledger_path in ledger_paths
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
    ]
    ledger = {row["address"]: row for row in ledger_rows}
    require(ledger["0x84BF1850"]["callees"] ==
            ["0x84BED488", "0x84D0859C"] and
            ledger["0x84BED488"]["callees"] == ["0x84BD6DCC"],
            "Ghidra direct-call ownership changed")

    trace_text = "".join(f"0x{pc:08X}\n" for pc in trace).encode("ascii")
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "scope": {
            "method": "nonexecuting path-specific static continuation",
            "translated_title_functions_called": False,
            "entry_called": False,
            "native_boot_proved": False,
            "main_menu_proved": False,
        },
        "start_state": {
            "pc": "0x84BF188C",
            "lr": "0x84BF188C",
            "r1": "0x7001FD10",
            "r3": "0x00000000",
            "r30": "0x00100000",
            "source": "proved guarded first-boundary adapter return",
            "prior_executed_guest_instructions": 38,
        },
        "static_trace": {
            "continuation_instruction_count_through_next_call": len(trace),
            "cumulative_instruction_count_through_next_call": 38 + len(trace),
            "unique_pc_count": len(set(trace)),
            "first_pc": f"0x{trace[0]:08X}",
            "last_pc": f"0x{trace[-1]:08X}",
            "ordered_pc_sha256": sha256_bytes(trace_text),
            "owners": origins,
            "direct_call_chain": [
                "sub_84BF1850", "sub_84BED488", "__savegprlr_21",
                "sub_84BD8410", "sub_84BD6E60",
            ],
            "unresolved_indirect_before_boundary": False,
            "opcode_candidate_before_boundary": False,
            "switch_tail_residue_before_boundary": False,
        },
        "branch_proof": [
            {"pc": "0x84BF1890", "condition": "r3 == 0",
             "outcome": "taken -> 0x84BF18A8"},
            {"pc": "0x84BF18D8", "condition": "[0x852D64A0] == 0",
             "outcome": "fall through and construct heap"},
            {"pc": "0x84BED4E4", "condition": "descriptor pointer != 0",
             "outcome": "fall through"},
            {"pc": "0x84BED4F8", "condition": "descriptor.size == 48",
             "outcome": "copy exact 48-byte descriptor"},
            {"pc": "0x84BD8418", "condition":
             "destination 0x7001FC80 < source 0x7001FD60",
             "outcome": "forward copy -> 0x84BD6E60"},
            {"pc": "0x84BED558", "condition":
             "([0x852D6484] & 0x00200000) == 0",
             "outcome": "feature override absent"},
            {"pc": "0x84BED600", "condition": "requested alignment 0x1000 != 0",
             "outcome": "round alignment to 0x10000"},
            {"pc": "0x84BED66C", "condition": "requested size 0x100000 != 0",
             "outcome": "round size to 0x100000"},
            {"pc": "0x84BED698", "condition": "requested base == 0",
             "outcome": "anonymous reserve path -> 0x84BED798"},
        ],
        "descriptor_and_frames": {
            "sub_84BF1850_stack": "0x7001FD10",
            "source_descriptor": "0x7001FD60",
            "source_descriptor_bytes": 48,
            "allocator_stack": "0x7001FC00",
            "copied_descriptor": "0x7001FC80",
            "heap_singleton_address": "0x852D64A0",
            "heap_singleton_initial_value": "0x00000000",
        },
        "next_boundary": {
            "classification": "typed_import",
            "library": "xboxkrnl.exe",
            "name": "NtAllocateVirtualMemory",
            "ordinal": 204,
            "thunk": "0x84D0863C",
            "call_pc": "0x84BED7B8",
            "return_pc": "0x84BED7BC",
            "arguments": {
                "r3_base_pointer": "0x7001FC50",
                "base_value_be_u32": "0x00000000",
                "r4_size_pointer": "0x7001FD34",
                "size_value_be_u32": "0x00100000",
                "r5_allocation_type": "0x60002000",
                "r6_protection": "0x00000004",
                "r7_debug_memory": "0x00000000",
            },
            "typed_leaf_adapter_exact_site_supported": True,
            "adapter_invoked_by_this_analysis": False,
            "runtime_requirement": (
                "preserve the configured 64-KiB guest VM arena and invoke the "
                "exact bounded reserve adapter before generated continuation"
            ),
        },
        "ordered_prerequisites": [
            {
                "order": 1,
                "requirement": (
                    "Add an isolated continuation gate that restores the exact "
                    "0x84BF188C state and retains the existing instruction and "
                    "function-dispatch ledgers."
                ),
            },
            {
                "order": 2,
                "requirement": (
                    "Authorize only the proved NtAllocateVirtualMemory site at "
                    "0x84BED7B8 and use the existing 0x40000000/0x10000000 "
                    "configured VM arena; verify both BE output words transactionally."
                ),
            },
            {
                "order": 3,
                "requirement": (
                    "After a successful reserve, continue only under the same "
                    "budgets and stop at the next typed/import/indirect/runtime "
                    "boundary; do not infer a title boot from allocation success."
                ),
            },
        ],
        "portme": [
            "// PORTME at 0x84BED7B8: resume through only the exact bounded NtAllocateVirtualMemory reserve adapter while preserving the same guest memory, VM ledger, stack, and instruction/function budgets.",
            "// PORTME at 0x84BED7BC: validate the adapter's big-endian base/size writes before allowing any later generated instruction to run.",
        ],
        "inputs": {
            "retail_xex": pin(xex, root),
            "retail_volume": {
                "path": relative(volume, root),
                "size": volume.stat().st_size,
                "sha256": EXPECTED_VOLUME_SHA256,
            },
            "decoded_image": {
                "size": decoded_path.stat().st_size,
                "sha256": EXPECTED_DECODED_SHA256,
                "temporary_validator_artifact": True,
                "preserved_by_analyzer": True,
            },
            "guarded_first_boundary_report": pin(guarded_path, root),
            "composed_report": pin(composed_path, root),
            "leaf_adapter_report": pin(leaf_path, root),
            "xex_import_report": pin(xex_report_path, root),
            "ghidra_ledgers": [pin(path, root) for path in ledger_paths],
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(
        "APF_SECOND_BOUNDARY_STATIC_REPORT "
        "start=0x84BF188C r3=0 next=NtAllocateVirtualMemory "
        "call=0x84BED7B8 return=0x84BED7BC thunk=0x84D0863C "
        f"continuation_instructions={len(trace)} cumulative={38 + len(trace)} "
        "executed=0 native_boot=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AnalysisError as error:
        raise SystemExit(f"apf_second_boundary_static: {error}")
