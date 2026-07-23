#!/usr/bin/env python3
"""Recompute APF's imported-data xrefs and bounded runtime seed frontier."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA = "apf2k8_imported_data_frontier/v1"
EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_XREFS_SHA256 = (
    "dffdd96da2e95a9025e6025d79d0c78ce46421da6233f2f2ad11d6061c7f1ad6"
)
EXPECTED_XREF_SCRIPT_SHA256 = (
    "295a93aeb726ff6e489eb2acc759b4bb1aa764793b71906cf8abb5a5c834e83b"
)
EXPECTED_RAW_XEX_PREFIX_SHA256 = (
    "1a5acdcfdf3a0b869a44b30fdd1a25fa1ed45a21dbd7b6292f6b81db1b1a7960"
)
EXPECTED_XENIA_COMMIT = "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"
EXPECTED_SLOT_COUNT = 13
EXPECTED_XREF_COUNT = 46


class ImportedDataError(RuntimeError):
    """Raised when a pinned imported-data invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ImportedDataError(message)


def sha256(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def pin(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": relative(path, root),
        "size": path.stat().st_size,
        "sha256": sha256(path),
    }


def git_head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    require(completed.stderr == "", "git rev-parse emitted stderr")
    return completed.stdout.strip()


def load_frontier_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(
        "apf_static_boot_import_frontier_for_data", path
    )
    require(spec is not None and spec.loader is not None,
            "cannot load direct-frontier module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_xref(raw: str) -> dict[str, object]:
    parts = raw.split(":", 4)
    if len(parts) == 5:
        instruction, owner, ghidra_name, ref_type, disassembly = parts
        require(owner != "none", "five-field xref unexpectedly lacks owner")
        owner_symbol = "sub_" + owner[2:].upper()
        return {
            "instruction_address": instruction,
            "owner_address": owner,
            "owner_symbol": owner_symbol,
            "ghidra_owner_name": ghidra_name,
            "reference_type": ref_type,
            "disassembly": disassembly,
        }
    require(len(parts) == 4 and parts[1] == "none",
            f"malformed imported-data xref: {raw}")
    instruction, _, ref_type, disassembly = parts
    return {
        "instruction_address": instruction,
        "owner_address": None,
        "owner_symbol": None,
        "ghidra_owner_name": None,
        "reference_type": ref_type,
        "disassembly": disassembly,
    }


def parse_xrefs(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        require(reader.fieldnames ==
                ["slot", "name", "raw_be32", "xref_count", "xrefs"],
                "imported-data xref columns changed")
        for raw in reader:
            xrefs = [parse_xref(item) for item in raw["xrefs"].split(";")
                     if item]
            require(len(xrefs) == int(raw["xref_count"]),
                    f"xref count changed for {raw['name']}")
            require(all(item["reference_type"] == "READ" for item in xrefs),
                    f"non-read xref found for {raw['name']}")
            rows.append({
                "slot": raw["slot"],
                "name": raw["name"],
                "raw_be32": raw["raw_be32"],
                "xref_count": len(xrefs),
                "xrefs": xrefs,
            })
    require(len(rows) == EXPECTED_SLOT_COUNT,
            "imported-data slot count changed")
    require(sum(int(row["xref_count"]) for row in rows) ==
            EXPECTED_XREF_COUNT, "imported-data xref total changed")
    return rows


def recompute_augmented_frontier(
    root: Path, indirect: dict[str, object]
) -> tuple[set[str], set[str], dict[str, str], dict[str, str]]:
    frontier_tool = root / "tools/apf_static_boot_import_frontier.py"
    module = load_frontier_module(frontier_tool)
    generated = root / "build-static-recomp-apf/ppc-filtered"
    numbered = [
        generated / f"ppc_recomp.{index}.cpp"
        for index in range(module.EXPECTED_NUMBERED_SOURCE_COUNT)
    ]
    require(all(path.is_file() for path in numbered),
            "generated translation unit is missing")
    calls, _, origins, bodies = module.parse_generated(numbered)

    xex_report = json.loads(
        (root / "reports/headers/apf2k8_xex_report.json").read_text(
            encoding="utf-8")
    )
    callable_symbols = {
        "__imp__" + str(item["name"])
        for item in xex_report["imports"]["items"]
        if item["thunk_address"] is not None
    }
    proved: dict[str, set[str]] = defaultdict(set)
    for site in indirect["original_indirect_sites"]:
        for target in site["proved_targets"]:
            proved[str(site["caller"])].add(str(target["symbol"]))

    reached_generated: set[str] = set()
    reached_imports: set[str] = set()
    pending: deque[str] = deque([module.ENTRY])
    while pending:
        caller = pending.popleft()
        if caller in reached_generated:
            continue
        require(caller in calls, f"frontier body is missing: {caller}")
        reached_generated.add(caller)
        if caller in module.BOUNDARIES:
            continue
        for callee in sorted(set(calls[caller]) | proved.get(caller, set())):
            if callee in calls:
                if callee not in reached_generated:
                    pending.append(callee)
            else:
                require(callee in callable_symbols,
                        f"unclassified frontier callee: {callee}")
                reached_imports.add(callee)
    require((len(reached_generated), len(reached_imports)) == (428, 30),
            "augmented 458-node frontier changed")
    return reached_generated, reached_imports, origins, bodies


def render_summary_tsv(rows: list[dict[str, object]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow([
        "slot", "name", "raw_be32", "xref_count",
        "distinct_owner_functions", "frontier_xref_count",
        "frontier_consumers", "bootstrap_state",
    ])
    for row in rows:
        owner_symbols = sorted({
            str(item["owner_symbol"])
            for item in row["xrefs"]
            if item["owner_symbol"] is not None
        })
        frontier_xrefs = [
            item for item in row["xrefs"]
            if bool(item["in_augmented_frontier"])
        ]
        frontier_consumers = sorted({
            str(item["owner_symbol"]) for item in frontier_xrefs
        })
        state = (
            "seeded_frontier_needed"
            if frontier_consumers
            else "preserved_retail_ordinal_outside_frontier"
        )
        writer.writerow([
            row["slot"], row["name"], row["raw_be32"],
            row["xref_count"], len(owner_symbols), len(frontier_xrefs),
            ";".join(frontier_consumers), state,
        ])
    return output.getvalue()


def build_report(root: Path) -> tuple[dict[str, object], str]:
    xrefs_path = root / "reports/static_recomp/apf2k8_imported_data_xrefs.tsv"
    xref_script = root / "tools/ghidra_scripts/apf/ApfImportedDataXrefs.java"
    xex_path = root / "extracted/All-Pro Football 2K8 (USA)/default.xex"
    xex_report_path = root / "reports/headers/apf2k8_xex_report.json"
    indirect_path = (
        root / "reports/static_recomp/apf2k8_boot_indirect_frontier.json"
    )
    pseudo_path = (
        root / "research/functions/apf2k8/pseudo_c/"
        "apf2k8_pseudoc_19968_20223.c"
    )
    generated_consumer_path = (
        root / "build-static-recomp-apf/ppc-filtered/ppc_recomp.217.cpp"
    )
    xenia = Path("/media/noah/Storage/.codex-tmp/xenia-source")
    local_paths = [
        root / "include/static_runtime/apf_imported_data_bootstrap.h",
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "tests/apf_imported_data_bootstrap_test.c",
    ]
    xenia_paths = [
        xenia / "src/xenia/kernel/xboxkrnl/xboxkrnl_table.inc",
        xenia / "src/xenia/kernel/xboxkrnl/xboxkrnl_module.cc",
        xenia / "src/xenia/kernel/kernel_state.cc",
        xenia / "src/xenia/kernel/xmodule.h",
        xenia / "src/xenia/kernel/user_module.cc",
    ]
    required = [xrefs_path, xref_script, xex_path, xex_report_path,
                indirect_path, pseudo_path, generated_consumer_path,
                *local_paths, *xenia_paths]
    require(all(path.is_file() for path in required), "required input is missing")
    require(sha256(xrefs_path) == EXPECTED_XREFS_SHA256,
            "canonical Ghidra xrefs changed")
    require(sha256(xref_script) == EXPECTED_XREF_SCRIPT_SHA256,
            "Ghidra xref script changed")
    require(sha256(xex_path) == EXPECTED_XEX_SHA256,
            "retail APF XEX changed")
    require(git_head(xenia) == EXPECTED_XENIA_COMMIT,
            "pinned Xenia commit changed")

    xex_report = json.loads(xex_report_path.read_text(encoding="utf-8"))
    require(xex_report["inputs"]["decompressed_pe_sha256"] ==
            EXPECTED_DECODED_SHA256, "decoded-image identity changed")
    require(xex_report["inputs"]["decompressed_pe_size"] ==
            54_001_664, "decoded-image size changed")
    indirect = json.loads(indirect_path.read_text(encoding="utf-8"))
    require(indirect["schema"] == "apf2k8_boot_indirect_frontier/v1",
            "indirect-frontier schema changed")
    require(indirect["result"]["augmented_total_nodes"] == 458,
            "augmented frontier size changed")
    require(indirect["result"]["translated_title_code_executed"] is False,
            "frontier analysis unexpectedly executed title code")

    raw_prefix = xex_path.read_bytes()[:144]
    require(len(raw_prefix) == 144 and raw_prefix[:4] == b"XEX2",
            "raw XEX prefix is missing")
    require(hashlib.sha256(raw_prefix).hexdigest() ==
            EXPECTED_RAW_XEX_PREFIX_SHA256, "raw XEX prefix changed")
    optional = [
        {
            "key": f"0x{int.from_bytes(raw_prefix[24 + index * 8:28 + index * 8], 'big'):08X}",
            "value_or_offset": f"0x{int.from_bytes(raw_prefix[28 + index * 8:32 + index * 8], 'big'):08X}",
        }
        for index in range(15)
    ]
    require(all(row["key"] != "0x00020401" for row in optional),
            "DEFAULT_HEAP_SIZE unexpectedly appears in retail XEX")

    reached_generated, reached_imports, origins, bodies = (
        recompute_augmented_frontier(root, indirect)
    )
    rows = parse_xrefs(xrefs_path)
    for row in rows:
        for item in row["xrefs"]:
            item["in_augmented_frontier"] = (
                item["owner_symbol"] in reached_generated
                if item["owner_symbol"] is not None else False
            )
    reached_rows = [row for row in rows if any(
        bool(item["in_augmented_frontier"]) for item in row["xrefs"]
    )]
    reached_xrefs = [
        (str(row["name"]), str(item["instruction_address"]),
         str(item["owner_symbol"]))
        for row in rows for item in row["xrefs"]
        if item["in_augmented_frontier"]
    ]
    require([str(row["name"]) for row in reached_rows] ==
            ["XexExecutableModuleHandle", "KeDebugMonitorData"],
            "frontier-needed imported-data set changed")
    require(reached_xrefs == [
        ("XexExecutableModuleHandle", "0x84BF186C", "sub_84BF1850"),
        ("KeDebugMonitorData", "0x84BF196C", "sub_84BF1950"),
    ], "frontier imported-data consumers changed")

    xex_body = bodies["sub_84BF1850"]
    debug_body = bodies["sub_84BF1950"]
    for fragment in (
        "// lwz r11,1964(r11)", "// lwz r11,0(r11)",
        "// lwz r3,88(r11)", "// ori r4,r4,1025",
        "ctx.lr = 0x84BF188C;", "__imp__RtlImageXexHeaderField(ctx, base);",
    ):
        require(fragment in xex_body,
                f"XEX consumer instruction changed: {fragment}")
    for fragment in (
        "// lwz r11,2368(r11)", "// lwz r11,0(r11)",
        "// cmplwi r11,0", "// beq 0x84bf1990",
        "// lwz r11,24(r11)", "PPC_CALL_INDIRECT_FUNC(ctx.ctr.u32);",
    ):
        require(fragment in debug_body,
                f"debug consumer instruction changed: {fragment}")

    xenia_texts = {path.name: path.read_text(encoding="utf-8")
                   for path in xenia_paths}
    require("0x00000059, KeDebugMonitorData" in
            xenia_texts["xboxkrnl_table.inc"],
            "Xenia debug-monitor ordinal changed")
    require("0x00000193, XexExecutableModuleHandle" in
            xenia_texts["xboxkrnl_table.inc"],
            "Xenia executable-module ordinal changed")
    require("if (!cvars::kernel_debug_monitor)" in
            xenia_texts["xboxkrnl_module.cc"] and
            "xe::store_and_swap<uint32_t>(lpKeDebugMonitorData, 0);" in
            xenia_texts["xboxkrnl_module.cc"],
            "Xenia debugger-disabled cell behavior changed")
    require("*variable_ptr = executable_module_->hmodule_ptr();" in
            xenia_texts["kernel_state.cc"],
            "Xenia executable-module cell assignment changed")
    require("xe::be<uint32_t> xex_header_base;    // 0x58" in
            xenia_texts["xmodule.h"],
            "Xenia LDR XEX-header offset changed")
    require("ldr_data->xex_header_base = guest_xex_header_;" in
            xenia_texts["user_module.cc"],
            "Xenia separate guest-XEX-header assignment changed")

    summary_tsv = render_summary_tsv(rows)
    report = {
        "schema": SCHEMA,
        "validation_date": "2026-07-11",
        "result": {
            "imported_data_slots_analyzed": len(rows),
            "direct_read_xrefs": sum(int(row["xref_count"]) for row in rows),
            "augmented_frontier_nodes":
                len(reached_generated) + len(reached_imports),
            "frontier_needed_slots": len(reached_rows),
            "frontier_consumer_xrefs": len(reached_xrefs),
            "slots_seeded_by_isolated_bootstrap": 2,
            "ordinal_slots_preserved": 11,
            "raw_xex_prefix_copied_to_separate_guest_storage": True,
            "default_heap_size_key_present": False,
            "debug_monitor_callback_dispatch_possible": False,
            "bootstrap_transactional": True,
            "title_entry_called": False,
            "translated_title_code_executed": False,
            "emulator_launched": False,
            "all_thirteen_imported_data_slots_resolved": False,
        },
        "inputs": {
            "retail_xex": pin(xex_path, root),
            "decoded_image": {
                "guest_base": "0x82000000",
                "size": 54_001_664,
                "sha256": EXPECTED_DECODED_SHA256,
                "first_magic": "MZ",
            },
            "raw_xex_prefix": {
                "source": relative(xex_path, root),
                "offset": 0,
                "size": 144,
                "sha256": EXPECTED_RAW_XEX_PREFIX_SHA256,
                "first_magic": "XEX2",
            },
            "ghidra_xref_script": pin(xref_script, root),
            "ghidra_xrefs": pin(xrefs_path, root),
            "indirect_frontier": pin(indirect_path, root),
            "generated_consumer_source": pin(generated_consumer_path, root),
            "pseudo_c_consumer_source": pin(pseudo_path, root),
            "isolated_bootstrap_sources": [pin(path, root) for path in local_paths],
            "pinned_xenia": {
                "commit": EXPECTED_XENIA_COMMIT,
                "license": "BSD-3-Clause",
                "sources": [pin(path, root) for path in xenia_paths],
            },
        },
        "corrected_address_model": {
            "decoded_pe_image": {
                "guest_base": "0x82000000",
                "magic": "MZ",
                "contains_import_slots": True,
                "is_raw_xex_header_view": False,
            },
            "raw_xex_header": {
                "magic": "XEX2",
                "copied_prefix_bytes": 144,
                "guest_address": "loader arena + 0x100",
            },
            "rejected_initial_assumption": (
                "LDR +0x58 = 0x82000000; rejected because that guest address "
                "is the decoded PE/MZ image, not a raw XEX2 header"
            ),
            "implemented_chain": (
                "title slot 0x820007AC -> arena export cell -> arena LDR "
                "module object -> LDR +0x58 -> separate arena XEX2 prefix"
            ),
            "xenia_match": (
                "UserModule copies the raw XEX header into guest SystemHeap, "
                "writes that distinct pointer to X_LDR_DATA_TABLE_ENTRY +0x58, "
                "and KernelState writes hmodule_ptr into the export cell"
            ),
        },
        "augmented_frontier": {
            "generated_nodes_including_boundaries": len(reached_generated),
            "callable_import_nodes": len(reached_imports),
            "total_nodes": len(reached_generated) + len(reached_imports),
            "imported_data_xrefs_are_not_call_graph_edges": True,
            "frontier_needed_slots": [str(row["name"]) for row in reached_rows],
            "frontier_consumers": [
                {"slot": name, "instruction_address": address,
                 "owner": owner}
                for name, address, owner in reached_xrefs
            ],
        },
        "slots": [
            {
                **row,
                "distinct_owner_functions": sorted({
                    str(item["owner_symbol"]) for item in row["xrefs"]
                    if item["owner_symbol"] is not None
                }),
                "frontier_consumers": sorted({
                    str(item["owner_symbol"]) for item in row["xrefs"]
                    if item["in_augmented_frontier"]
                }),
                "bootstrap_state": (
                    "seeded_frontier_needed"
                    if any(item["in_augmented_frontier"] for item in row["xrefs"])
                    else "preserved_retail_ordinal_outside_frontier"
                ),
            }
            for row in rows
        ],
        "consumer_evidence": {
            "sub_84BF1850": {
                "generated_source": origins["sub_84BF1850"][0],
                "slot_load": "0x84BF186C: lwz r11,0x7AC(r11)",
                "export_cell_deref": "0x84BF1870: lwz r11,0(r11)",
                "module_null_guard": "0x84BF1874/0x84BF1878",
                "xex_header_load": "0x84BF1880: lwz r3,0x58(r11)",
                "requested_key_build": "0x84BF187C/0x84BF1884 -> 0x00020401",
                "import_call": "0x84BF1888: RtlImageXexHeaderField",
                "import_return_address": "0x84BF188C",
                "retail_optional_header_count": 15,
                "retail_optional_headers": optional,
                "default_heap_size_absent": True,
                "bounded_leaf_adapter_result": "r3 = NULL",
            },
            "sub_84BF1950": {
                "generated_source": origins["sub_84BF1950"][0],
                "slot_load": "0x84BF196C: lwz r11,0x940(r11)",
                "export_cell_deref": "0x84BF1970: lwz r11,0(r11)",
                "object_null_guard": "0x84BF1974/0x84BF1978",
                "callback_load_if_nonnull": "0x84BF197C: lwz r11,0x18(r11)",
                "callback_call_if_nonnull": "0x84BF198C: bctrl",
                "debugger_disabled_export_cell_value": 0,
                "callback_field_read": False,
                "callback_dispatch_possible": False,
            },
        },
        "bootstrap_contract": {
            "debugger_configuration": "explicitly disabled only",
            "arena_alignment": 4096,
            "arena_minimum_bytes": 400,
            "arena_layout": [
                {"offset": "0x000", "object": "XexExecutableModuleHandle export cell", "bytes": 4},
                {"offset": "0x010", "object": "X_LDR_DATA_TABLE_ENTRY-compatible module object", "bytes": 100},
                {"offset": "0x080", "object": "KeDebugMonitorData export cell", "bytes": 4},
                {"offset": "0x100", "object": "retail raw-XEX prefix copy", "bytes": 144},
            ],
            "preflight": [
                "SHA-256 exact 54,001,664-byte decoded image",
                "all 13 exact retail big-endian ordinal words",
                "SHA-256 exact 144-byte raw XEX prefix",
                "fresh zero-filled used arena span",
                "guest u32 bounds and 4 KiB arena alignment",
                "guest disjointness from title image and static dispatch table",
                "host non-aliasing between image, prefix, and arena",
            ],
            "writes_after_complete_preflight": [
                "replace only title slots 0x820007AC and 0x82000940",
                "seed export-cell/module/prefix/debug-cell arena state",
                "leave the other 11 title ordinal words byte-exact",
            ],
            "failure_policy": "no title bytes, arena bytes, or result bytes mutate",
        },
        "worked": [
            "Recomputed the exact 428-generated + 30-callable-import augmented frontier.",
            "Classified all 46 Ghidra direct reads of the 13 imported-data slots.",
            "Proved only sub_84BF1850 and sub_84BF1950 consume imported data in that frontier.",
            "Implemented a two-slot transactional seed with eleven ordinal words preserved.",
            "Copied the pinned raw XEX prefix to a distinct guest arena object and rejected the decoded-image overlay model.",
            "Reached the existing bounded absent DEFAULT_HEAP_SIZE adapter and obtained NULL in the standalone test.",
            "Proved the explicit debugger-disabled KeDebugMonitorData cell prevents the +0x18 callback read and dispatch.",
        ],
        "failed_or_unproved": [
            "The eleven outside-frontier imported data variables are not runtime-resolved.",
            "Debugger-enabled KeDebugMonitorData layout and callback ABI are unsupported.",
            "No title function, title entry, emulator, renderer, menu, or gameplay path was executed.",
            "The 458-node frontier is path-insensitive and is not a successful boot trace.",
        ],
        "portme": [
            "// PORTME: seed each of the remaining 11 imported-data variables only when a reached consumer and exact XDK object/value contract are proved.",
            "// PORTME at 0x84BF198C: implement the debugger-enabled KeDebugMonitorData +0x18 callback ABI before allowing a nonzero debug-monitor object.",
            "// PORTME: retain the raw XEX header in loader-owned guest storage for the complete runtime lifetime; never point LDR +0x58 at the decoded PE base.",
            "// PORTME: do not call _xstart until callable imports, remaining indirect sites, scheduling, exceptions, devices, and guest address ownership are complete.",
        ],
    }
    return report, summary_tsv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--tsv-output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    report, summary_tsv = build_report(root)
    report_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report_output is None:
        print(report_text, end="")
    else:
        args.report_output.write_text(report_text, encoding="utf-8")
    if args.tsv_output is not None:
        args.tsv_output.write_text(summary_tsv, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
