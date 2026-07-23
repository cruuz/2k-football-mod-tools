#!/usr/bin/env python3
"""Produce the fail-closed APF first-entry integration/readiness report.

This is a static and non-title audit.  It reconstructs the augmented _xstart
closure, cross-checks opcode and switch-tail residue ownership, verifies the
exact first typed boundary, and consumes transcripts from isolated mapping and
link probes.  It never invokes _xstart.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "apf2k8_first_entry_readiness/v1"
EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_ENTRY = "_xstart"
EXPECTED_FIRST_CALL = 0x84BF1888
EXPECTED_FIRST_RETURN = 0x84BF188C
EXPECTED_FIRST_THUNK = 0x84D0859C
EXPECTED_PROBE_PREFIX = "APF_FIRST_ENTRY_PROBE_PASS "
EXPECTED_LINK_PREFIX = "APF_FIRST_ENTRY_LINK_PASS "


class ReadinessError(RuntimeError):
    """Raised when a pinned input or proof invariant changed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReadinessError(message)


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def load_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("apf_frontier", path)
    require(spec is not None and spec.loader is not None,
            "cannot load frontier parser")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transcript_line(path: Path | None, prefix: str) -> str | None:
    if path is None:
        return None
    require(path.is_file(), f"probe transcript is missing: {path}")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if line.startswith(prefix)]
    require(len(lines) == 1, f"probe transcript lacks one {prefix!r} line")
    return lines[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--xex", type=Path, default=Path(
        "extracted/All-Pro Football 2K8 (USA)/default.xex"))
    parser.add_argument("--generated", type=Path,
                        default=Path("build-static-recomp-apf/ppc-filtered"))
    parser.add_argument("--switch-candidate", type=Path, default=Path(
        "build-static-recomp-apf/ppc-switch-tail-candidate"))
    parser.add_argument("--frontier-tool", type=Path, default=Path(
        "tools/apf_static_boot_import_frontier.py"))
    parser.add_argument("--xex-report", type=Path, default=Path(
        "reports/headers/apf2k8_xex_report.json"))
    parser.add_argument("--indirect-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_boot_indirect_frontier.json"))
    parser.add_argument("--imported-data-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_imported_data_frontier.json"))
    parser.add_argument("--adapter-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_boot_leaf_adapters.json"))
    parser.add_argument("--opcode-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_opcode_candidates_composed.json"))
    parser.add_argument("--opcode-sites", type=Path, default=Path(
        "reports/static_recomp/apf2k8_opcode_gap_sites.tsv"))
    parser.add_argument("--switch-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_static_recomp_switch_tail_dispatch.json"))
    parser.add_argument("--switch-residue", type=Path, default=Path(
        "reports/static_recomp/apf2k8_static_recomp_switch_tail_residue.tsv"))
    parser.add_argument("--probe-transcript", type=Path)
    parser.add_argument("--link-transcript", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    resolve = lambda path: path.resolve() if path.is_absolute() else \
        (root / path).resolve()
    xex = resolve(args.xex)
    generated = resolve(args.generated)
    switch_candidate = resolve(args.switch_candidate)
    frontier_tool = resolve(args.frontier_tool)
    xex_report_path = resolve(args.xex_report)
    indirect_report_path = resolve(args.indirect_report)
    imported_data_path = resolve(args.imported_data_report)
    adapter_path = resolve(args.adapter_report)
    opcode_report_path = resolve(args.opcode_report)
    opcode_sites_path = resolve(args.opcode_sites)
    switch_report_path = resolve(args.switch_report)
    switch_residue_path = resolve(args.switch_residue)
    probe_path = resolve(args.probe_transcript) \
        if args.probe_transcript is not None else None
    link_path = resolve(args.link_transcript) \
        if args.link_transcript is not None else None
    output = resolve(args.json)
    required_files = [
        xex, frontier_tool, xex_report_path, indirect_report_path,
        imported_data_path, adapter_path, opcode_report_path,
        opcode_sites_path, switch_report_path, switch_residue_path,
        root / "include/static_runtime/apf_first_entry_gate.h",
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "include/static_runtime/apf_first_entry_xenon_bridge.h",
        root / "src/static_runtime/apf_first_entry_xenon_bridge.cpp",
        root / "tools/apf_first_entry_gate_probe.c",
        root / "tests/apf_first_entry_gate_test.c",
    ]
    require(all(path.is_file() for path in required_files),
            "required readiness input is missing")
    require(generated.is_dir() and switch_candidate.is_dir(),
            "generated source tree is missing")
    require(sha256_file(xex) == EXPECTED_XEX_SHA256,
            "retail XEX hash changed")

    frontier = load_module(frontier_tool)
    numbered = [generated / f"ppc_recomp.{index}.cpp"
                for index in range(frontier.EXPECTED_NUMBERED_SOURCE_COUNT)]
    require(all(path.is_file() for path in numbered),
            "baseline generated TU is missing")
    calls, indirect_counts, origins, bodies = frontier.parse_generated(numbered)
    require(frontier.ENTRY == EXPECTED_ENTRY, "entry symbol changed")
    xex_report = json.loads(xex_report_path.read_text(encoding="utf-8"))
    callable_imports = {
        "__imp__" + item["name"] for item in xex_report["imports"]["items"]
        if item["thunk_address"] is not None
    }
    indirect_report = json.loads(
        indirect_report_path.read_text(encoding="utf-8"))
    proved_edges: dict[str, set[str]] = defaultdict(set)
    for site in indirect_report["original_indirect_sites"]:
        for target in site["proved_targets"]:
            proved_edges[site["caller"]].add(target["symbol"])

    reached_generated: set[str] = set()
    reached_imports: set[str] = set()
    pending: deque[str] = deque([frontier.ENTRY])
    while pending:
        caller = pending.popleft()
        if caller in reached_generated:
            continue
        require(caller in calls, f"frontier body missing: {caller}")
        reached_generated.add(caller)
        if caller in frontier.BOUNDARIES:
            continue
        for callee in set(calls[caller]) | proved_edges.get(caller, set()):
            if callee in calls:
                pending.append(callee)
            elif callee in callable_imports:
                reached_imports.add(callee)
            else:
                raise ReadinessError(f"unclassified frontier edge: {callee}")
    active = reached_generated - frontier.BOUNDARIES
    require((len(reached_generated), len(active), len(reached_imports)) ==
            (428, 426, 30), "augmented frontier counts changed")

    preboundary_symbols = [
        "_xstart", "__savegprlr_28", "sub_84BF1950", "sub_84BF1850"
    ]
    require(all(symbol in active for symbol in preboundary_symbols),
            "pre-boundary symbol left augmented frontier")
    xstart = bodies["_xstart"]
    first_parent = bodies["sub_84BF1950"]
    first_consumer = bodies["sub_84BF1850"]
    require("sub_84BF1950(ctx, base);" in xstart and
            "sub_84BF1850(ctx, base);" in first_parent and
            "ctx.lr = 0x84BF188C;" in first_consumer and
            "__imp__RtlImageXexHeaderField(ctx, base);" in first_consumer,
            "exact first-boundary generated sequence changed")
    before_import = first_consumer.split(
        "__imp__RtlImageXexHeaderField(ctx, base);", 1)[0]
    require("PPC_CALL_INDIRECT_FUNC" not in before_import,
            "indirect dispatch appeared before first typed boundary")

    imported_data = json.loads(imported_data_path.read_text(encoding="utf-8"))
    consumer = imported_data["consumer_evidence"]["sub_84BF1850"]
    require(consumer["import_call"] ==
            f"0x{EXPECTED_FIRST_CALL:08X}: RtlImageXexHeaderField" and
            consumer["import_return_address"] ==
            f"0x{EXPECTED_FIRST_RETURN:08X}" and
            consumer["default_heap_size_absent"] is True and
            consumer["bounded_leaf_adapter_result"] == "r3 = NULL",
            "imported-data first-boundary evidence changed")

    opcode_rows = list(csv.DictReader(
        opcode_sites_path.open(encoding="utf-8"), delimiter="\t"))
    for row in opcode_rows:
        row["owner_symbol"] = "sub_" + row["function_start"][2:].upper()
    frontier_opcode = [row for row in opcode_rows
                       if row["owner_symbol"] in active]
    preboundary_opcode = [row for row in opcode_rows
                          if row["owner_symbol"] in preboundary_symbols]
    require(not frontier_opcode and not preboundary_opcode,
            "opcode-gap site entered first-entry frontier")

    residue_rows = list(csv.DictReader(
        switch_residue_path.open(encoding="utf-8"), delimiter="\t"))
    portme = re.compile(
        r"PORTME: unresolved cross-function switch target "
        r"(0x[0-9A-F]+) from bctr (0x[0-9A-F]+)")
    function = re.compile(
        r"PPC_FUNC_IMPL\(__imp__(?:__)?(sub_[0-9A-F]+|_xstart)\)")
    switch_owners: list[dict[str, str]] = []
    for source in sorted(switch_candidate.glob("ppc_recomp.*.cpp")):
        owner: str | None = None
        for line in source.read_text(encoding="utf-8").splitlines():
            match = function.search(line)
            if match:
                owner = match.group(1)
            match = portme.search(line)
            if match:
                require(owner is not None, "switch PORTME lacks owner")
                switch_owners.append({
                    "target": match.group(1), "bctr": match.group(2),
                    "owner": owner, "source": source.name,
                })
    require(len(switch_owners) == 1076,
            "switch-tail candidate PORTME count changed")
    frontier_switch = [row for row in switch_owners
                       if row["owner"] in active]
    preboundary_switch = [row for row in switch_owners
                          if row["owner"] in preboundary_symbols]
    require(not frontier_switch and not preboundary_switch,
            "switch-tail residue entered first-entry frontier")

    unresolved_indirect = [
        site for site in indirect_report["original_indirect_sites"]
        if site["classification"] != "proved_bounded" and
        site["caller"] in active
    ] + indirect_report["augmented_frontier"]["newly_exposed_indirect_sites"]
    preboundary_indirect = [site for site in unresolved_indirect
                            if site["caller"] in preboundary_symbols and
                            int(site["call_instruction_address"], 0) <
                            EXPECTED_FIRST_CALL]
    require(len(unresolved_indirect) == 7 and not preboundary_indirect,
            "unresolved-indirect ordering changed")

    opcode_report = json.loads(opcode_report_path.read_text(encoding="utf-8"))
    switch_report = json.loads(switch_report_path.read_text(encoding="utf-8"))
    adapter_report = json.loads(adapter_path.read_text(encoding="utf-8"))
    require(opcode_report["composition"]["switch_tail_candidate_included"]
            is False, "opcode report now claims switch composition")
    require(switch_report["result"]["remaining_portme_occurrences"] == 1076,
            "switch residue report changed")
    require(adapter_report["result"]["classified_frontier_import_count"] == 30,
            "adapter import count changed")

    probe = transcript_line(probe_path, EXPECTED_PROBE_PREFIX)
    link = transcript_line(link_path, EXPECTED_LINK_PREFIX)
    if probe is not None:
        require("mapped_bytes=4294967296" in probe and
                "seeded_imports=2" in probe and "bindings=30" in probe and
                "first_call=0x84BF1888" in probe and
                "first_thunk=0x84D0859C" in probe and
                "adapter_status=ok" in probe and
                "entry_authorized=0" in probe and "entry_called=0" in probe,
                "mapping probe transcript changed")
    if link is not None:
        require("mappings=60731" in link and "typed_bindings=30" in link and
                "entry_authorized=0" in link and "entry_called=0" in link,
                "link probe transcript changed")

    bridge_source = root / "src/static_runtime/apf_first_entry_xenon_bridge.cpp"
    bridge_text = bridge_source.read_text(encoding="utf-8")
    bridge_definition_count = sum(
        line.lstrip().startswith("VC_APF_DEFINE_IMPORT(__imp__")
        for line in bridge_text.splitlines()
    )
    require(bridge_definition_count == 30,
            "typed Xenon bridge definition count changed")
    generated_budget_reference_count = sum(
        "vc_apf_first_entry_consume_budget" in path.read_text(encoding="utf-8")
        for path in numbered
    )
    require(generated_budget_reference_count == 0,
            "generated corpus unexpectedly gained budget instrumentation")

    blockers = [{
        "order": 1,
        "code": "COMPOSED_DERIVED_CORPUS",
        "portme": (
            "// PORTME: regenerate one isolated corpus with both the composed "
            "opcode candidate and switch-tail candidate applied; current "
            "candidate corpora remain separate even though neither residue "
            "set intersects the bounded first-entry frontier."
        ),
    }]
    if link is None:
        blockers.append({
            "order": len(blockers) + 1,
            "code": "GENERATED_DISPATCH_BRIDGE_LINK",
            "portme": (
                "// PORTME: link all 60,731 generated mappings against the "
                "30 typed bridge definitions and prove the guest lookup table "
                "contains those exact function pointers."
            ),
        })
    blockers.append({
        "order": len(blockers) + 1,
        "code": "INSTRUCTION_BUDGET_INSTRUMENTATION",
        "portme": (
            "// PORTME: instrument every executed guest instruction in the "
            "isolated derived corpus; the bounded ledger exists, but no "
            "generated translation unit consumes it yet."
        ),
    })

    report = {
        "schema": SCHEMA,
        "result": {
            "exact_first_typed_boundary_proved": True,
            "first_typed_boundary_adapter_probed": probe is not None,
            "guest_address_space_exactly_mapped": probe is not None,
            "raw_xex_header_separately_installed": probe is not None,
            "frontier_imported_data_slots_installed": 2 if probe else 0,
            "frontier_import_thunks_bound": 30,
            "generated_dispatch_mapping_count_installed":
                60731 if link else 0,
            "augmented_frontier_generated_nodes": len(active),
            "augmented_frontier_opcode_gap_sites": len(frontier_opcode),
            "augmented_frontier_unresolved_switch_occurrences":
                len(frontier_switch),
            "preboundary_unresolved_indirect_sites":
                len(preboundary_indirect),
            "ordered_blocker_count": len(blockers),
            "entry_call_authorized": False,
            "entry_called": False,
            "translated_title_code_executed": False,
            "first_boundary_reached_by_generated_execution": False,
            "native_boot_proved": False,
        },
        "execution_order": {
            "entry": "0x84BE9D08",
            "preboundary_generated_symbols": preboundary_symbols,
            "ordered_steps": [
                {"order": 1, "symbol": "_xstart",
                 "action": "establish 496-byte frame and call sub_84BF1950"},
                {"order": 2, "symbol": "sub_84BF1950",
                 "action": "establish 96-byte frame and call sub_84BF1850"},
                {"order": 3, "symbol": "sub_84BF1850",
                 "action": "establish 160-byte frame; load seeded module/header"},
                {"order": 4, "instruction": "0x84BF1888",
                 "return_address": "0x84BF188C",
                 "thunk": "0x84D0859C",
                 "import": "RtlImageXexHeaderField",
                 "action": "first typed boundary; stop after adapter"},
            ],
            "maximum_nested_frame_bytes_before_boundary": 752,
            "loader_stack_bytes": 131072,
            "indirect_dispatch_before_boundary": False,
            "execution_order_basis": (
                "exact generated source plus the SHA-pinned imported-data "
                "bootstrap pointer graph; no runtime trace is claimed"
            ),
        },
        "semantic_intersections": {
            "opcode_gap_site_count_global": len(opcode_rows),
            "opcode_gap_sites_in_augmented_frontier": len(frontier_opcode),
            "opcode_gap_sites_in_preboundary_symbols": len(preboundary_opcode),
            "switch_tail_residue_rows_global": len(residue_rows),
            "switch_tail_residue_occurrences_global": len(switch_owners),
            "switch_tail_residue_in_augmented_frontier": len(frontier_switch),
            "switch_tail_residue_in_preboundary_symbols":
                len(preboundary_switch),
            "unresolved_indirect_sites_in_augmented_frontier":
                len(unresolved_indirect),
            "unresolved_indirect_sites_before_first_boundary":
                len(preboundary_indirect),
            "unresolved_indirect_sites_after_or_off_first_boundary_path": [
                {"address": site["call_instruction_address"],
                 "caller": site["caller"]}
                for site in unresolved_indirect
            ],
        },
        "isolated_harness": {
            "normal_host_shell_linked": False,
            "sparse_guest_bytes": 0x100000000,
            "decoded_image_base": "0x82000000",
            "decoded_image_bytes": 0x03380000,
            "static_dispatch_base": "0x85380000",
            "static_dispatch_bytes": 0x00DB3000,
            "loader_stack_base": "0x70000000",
            "loader_stack_bytes": 0x00020000,
            "loader_arena_base": "0x70020000",
            "loader_arena_bytes": 0x00001000,
            "guest_thread_object": "0x70020200",
            "typed_import_binding_count": bridge_definition_count,
            "mapping_probe_passed": probe is not None,
            "generated_link_probe_passed": link is not None,
            "child_process_crash_timeout_containment_implemented": True,
            "instruction_budget_ledger_implemented": True,
            "function_dispatch_budget_ledger_implemented": True,
            "generated_instruction_budget_instrumented": False,
            "entry_call_api_present": False,
        },
        "ordered_blockers": blockers,
        "inputs": {
            "retail_xex": {
                "path": relative(xex, root),
                "sha256": sha256_file(xex),
            },
            "generated_directory": relative(generated, root),
            "switch_candidate_directory": relative(switch_candidate, root),
            "reports": [relative(path, root) for path in [
                indirect_report_path, imported_data_path, adapter_path,
                opcode_report_path, switch_report_path,
            ]],
            "probe_transcript_consumed": probe is not None,
            "link_transcript_consumed": link is not None,
            "local_files": [{
                "path": relative(path, root),
                "sha256": sha256_file(path),
            } for path in required_files[10:]],
        },
        "portme": [item["portme"] for item in blockers],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(
        "APF_FIRST_ENTRY_READINESS_REPORT_PASS "
        f"frontier_nodes={len(active)} opcode_frontier={len(frontier_opcode)} "
        f"switch_frontier={len(frontier_switch)} "
        f"preboundary_indirect={len(preboundary_indirect)} "
        f"bindings={bridge_definition_count} blockers={len(blockers)} "
        "entry_authorized=0 entry_called=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
