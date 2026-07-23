#!/usr/bin/env python3
"""Measure APF 2K8's direct-call import frontier around title entry.

This is a static planning analysis of the pinned XenonRecomp C++ corpus.  It
does not execute translated code and it deliberately does not infer targets
for PPC_CALL_INDIRECT_FUNC.  Function bodies at the title-main and post-main
boundaries are kept as opaque reached nodes for the narrowed closure.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "apf2k8_static_boot_import_frontier/v1"
EXPECTED_NUMBERED_SOURCE_COUNT = 236
EXPECTED_IMPLEMENTATION_COUNT = 60_397
EXPECTED_MAPPING_COUNT = 60_731
EXPECTED_DIRECT_CALL_SITE_COUNT = 116_970
EXPECTED_UNIQUE_DIRECT_EDGE_COUNT = 85_643
EXPECTED_INDIRECT_CALL_SITE_COUNT = 3_589
EXPECTED_CPP_MANIFEST_SHA256 = (
    "5e90f504e1291e3bcc2ba2e3688da07d44ba7b7bfbf10ac62beffb48d1e79132"
)
EXPECTED_GENERATED_TREE_SHA256 = (
    "6ac280d3fa0c6f016011ff176089ddbee4df4077c366a69623d9556db0e54599"
)
EXPECTED_MAPPING_SHA256 = (
    "9050c9a14781b40e0329ed9abca512f780cfba6ca709c8e8326397a66de6b5bd"
)
EXPECTED_XEX_REPORT_SHA256 = (
    "dfd21f9db2fdb683b2dbd0390d351fdac84ba1e796a0e0c5e0e60c28827f3f1c"
)

ENTRY = "_xstart"
TITLE_MAIN = "sub_84B8B1D0"
POST_MAIN = "sub_84BDAC80"
BOUNDARIES = {TITLE_MAIN, POST_MAIN}

NUMBERED_SOURCE = re.compile(r"^ppc_recomp\.(\d+)\.cpp$")
IMPLEMENTATION = re.compile(
    r"^PPC_FUNC_IMPL\(([^)]+)\)\s*\{", re.MULTILINE
)
ALIAS = re.compile(
    r'__attribute__\(\(alias\("([^"]+)"\)\)\) '
    r"PPC_WEAK_FUNC\(([^)]+)\);"
)
DIRECT_CALL = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\(ctx, base\);\s*$", re.MULTILINE
)
ANY_DIRECT_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\(ctx, base\)")
INDIRECT_CALL = re.compile(r"\bPPC_CALL_INDIRECT_FUNC\s*\(")
LINK_REGISTER = re.compile(r"ctx\.lr = 0x([0-9A-Fa-f]+);")
MAPPING = re.compile(
    r"\{\s*0x([0-9A-Fa-f]+),\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}"
)


class FrontierError(RuntimeError):
    """Raised when pinned inputs or structural invariants have changed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FrontierError(message)


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def manifest_digest(rows: list[dict[str, Any]]) -> str:
    state = hashlib.sha256()
    for row in rows:
        state.update(str(row["name"]).encode("utf-8") + b"\0")
        state.update(int(row["size"]).to_bytes(8, "big"))
        state.update(bytes.fromhex(str(row["sha256"])))
    return state.hexdigest()


def normalize_implementation(internal: str) -> str:
    require(internal.startswith("__imp__"),
            f"implementation lacks generated alias prefix: {internal}")
    return internal[len("__imp__"):]


def parse_generated(
    numbered_sources: list[Path],
) -> tuple[
    dict[str, list[str]],
    dict[str, int],
    dict[str, tuple[str, str]],
    dict[str, str],
]:
    """Return ordered calls, indirect-site counts, origins, and raw bodies."""
    calls: dict[str, list[str]] = {}
    indirect_sites: dict[str, int] = {}
    origins: dict[str, tuple[str, str]] = {}
    bodies: dict[str, str] = {}
    alias_pairs: set[tuple[str, str]] = set()

    for source in numbered_sources:
        text = source.read_text(encoding="utf-8")
        matches = list(IMPLEMENTATION.finditer(text))
        aliases = ALIAS.findall(text)
        alias_pairs.update(aliases)
        require(len(aliases) == len(matches),
                f"alias/implementation count differs in {source.name}")
        broad_calls = len(ANY_DIRECT_CALL.findall(text))
        anchored_calls = len(DIRECT_CALL.findall(text))
        require(broad_calls == anchored_calls,
                f"unparsed direct-call syntax in {source.name}")

        for index, match in enumerate(matches):
            internal = match.group(1)
            public = normalize_implementation(internal)
            end = matches[index + 1].start() if index + 1 < len(matches) \
                else len(text)
            body = text[match.end():end]
            require(public not in calls, f"duplicate implementation: {public}")
            calls[public] = DIRECT_CALL.findall(body)
            indirect_sites[public] = len(INDIRECT_CALL.findall(body))
            origins[public] = (source.name, internal)
            bodies[public] = body

    require(len(calls) == EXPECTED_IMPLEMENTATION_COUNT,
            "generated implementation count changed")
    require(len(alias_pairs) == EXPECTED_IMPLEMENTATION_COUNT,
            "generated alias pair count changed")
    expected_pairs = {
        (internal, public) for public, (_, internal) in origins.items()
    }
    require(alias_pairs == expected_pairs,
            "public aliases no longer match implementation names")
    return calls, indirect_sites, origins, bodies


def closure(
    calls: dict[str, list[str]],
    callable_imports: set[str],
    boundaries: set[str],
) -> tuple[set[str], set[str]]:
    """Direct-call closure; include boundary nodes, but do not descend them."""
    generated = set(calls)
    reached_generated: set[str] = set()
    reached_imports: set[str] = set()
    pending: deque[str] = deque([ENTRY])
    while pending:
        caller = pending.popleft()
        if caller in reached_generated:
            continue
        require(caller in generated, f"closure reached missing body: {caller}")
        reached_generated.add(caller)
        if caller in boundaries:
            continue
        for callee in sorted(set(calls[caller])):
            if callee in generated:
                if callee not in reached_generated:
                    pending.append(callee)
            elif callee in callable_imports:
                reached_imports.add(callee)
            else:
                raise FrontierError(f"unclassified direct callee: {callee}")
    return reached_generated, reached_imports


def closure_summary(
    calls: dict[str, list[str]],
    indirect_sites: dict[str, int],
    callable_imports: set[str],
    boundaries: set[str],
) -> tuple[dict[str, Any], set[str], set[str]]:
    reached_generated, reached_imports = closure(
        calls, callable_imports, boundaries
    )
    active = reached_generated - boundaries
    sites = [(caller, callee) for caller in active for callee in calls[caller]]
    edges = set(sites)
    generated = set(calls)
    generated_edges = {(a, b) for a, b in edges if b in generated}
    import_edges = {(a, b) for a, b in edges if b in callable_imports}
    external_edges = edges - generated_edges - import_edges
    require(not external_edges, "closure contains unclassified direct edges")
    import_sites = sum(b in callable_imports for _, b in sites)
    summary = {
        "generated_nodes_including_opaque_boundaries": len(reached_generated),
        "opaque_boundary_node_count": len(reached_generated & boundaries),
        "descended_generated_node_count": len(active),
        "callable_import_nodes": len(reached_imports),
        "total_nodes_including_imports": (
            len(reached_generated) + len(reached_imports)
        ),
        "direct_call_sites_from_descended_nodes": len(sites),
        "unique_direct_edges_from_descended_nodes": len(edges),
        "unique_generated_edges": len(generated_edges),
        "callable_import_call_sites": import_sites,
        "unique_callable_import_edges": len(import_edges),
        "unclassified_direct_edge_count": 0,
        "indirect_dispatch_sites_in_descended_nodes": sum(
            indirect_sites[name] for name in active
        ),
        "descended_nodes_with_indirect_dispatch": sum(
            indirect_sites[name] > 0 for name in active
        ),
    }
    return summary, reached_generated, reached_imports


def xstart_sequence(
    body: str,
    generated: set[str],
    callable_imports: set[str],
) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    pending_return: int | None = None
    for line in body.splitlines():
        if match := LINK_REGISTER.search(line):
            pending_return = int(match.group(1), 16)
        match = re.fullmatch(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\(ctx, base\);\s*", line
        )
        if not match:
            continue
        callee = match.group(1)
        require(pending_return is not None,
                f"entry call has no preceding LR assignment: {callee}")
        if callee in BOUNDARIES:
            classification = "opaque_boundary"
        elif callee in generated:
            classification = "generated_implementation"
        elif callee in callable_imports:
            classification = "callable_import"
        else:
            raise FrontierError(f"unclassified entry call: {callee}")
        sequence.append({
            "source_order": len(sequence) + 1,
            "call_instruction_address": f"0x{pending_return - 4:08X}",
            "return_address": f"0x{pending_return:08X}",
            "callee": callee,
            "classification": classification,
        })
        pending_return = None
    return sequence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--generated", type=Path,
                        default=Path("build-static-recomp-apf/ppc-filtered"))
    parser.add_argument("--xex-report", type=Path,
                        default=Path("reports/headers/apf2k8_xex_report.json"))
    parser.add_argument("--all-tus-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_static_recomp_all_tus.json"))
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    generated_dir = (root / args.generated).resolve() \
        if not args.generated.is_absolute() else args.generated.resolve()
    xex_report_path = (root / args.xex_report).resolve() \
        if not args.xex_report.is_absolute() else args.xex_report.resolve()
    all_tus_path = (root / args.all_tus_report).resolve() \
        if not args.all_tus_report.is_absolute() else args.all_tus_report.resolve()
    require(generated_dir.is_dir(), "generated C++ directory is missing")
    require(xex_report_path.is_file(), "XEX report is missing")
    require(all_tus_path.is_file(), "all-TU report is missing")
    require(sha256_file(xex_report_path) == EXPECTED_XEX_REPORT_SHA256,
            "pinned XEX report changed")

    numbered_by_index: dict[int, Path] = {}
    for path in generated_dir.glob("ppc_recomp.*.cpp"):
        if match := NUMBERED_SOURCE.match(path.name):
            numbered_by_index[int(match.group(1))] = path
    require(sorted(numbered_by_index) == list(range(EXPECTED_NUMBERED_SOURCE_COUNT)),
            "numbered source roster is not contiguous 0..235")
    numbered_sources = [
        numbered_by_index[index] for index in range(EXPECTED_NUMBERED_SOURCE_COUNT)
    ]
    mapping_path = generated_dir / "ppc_func_mapping.cpp"
    require(mapping_path.is_file(), "function mapping source is missing")
    require(sha256_file(mapping_path) == EXPECTED_MAPPING_SHA256,
            "function mapping source changed")

    manifest: list[dict[str, Any]] = []
    for path in [mapping_path, *numbered_sources]:
        manifest.append({
            "name": path.name,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    manifest_sha256 = manifest_digest(manifest)
    require(manifest_sha256 == EXPECTED_CPP_MANIFEST_SHA256,
            "generated C++ manifest changed")
    all_tus = json.loads(all_tus_path.read_text(encoding="utf-8"))
    require(all_tus["inputs"]["cpp_manifest_sha256"] == manifest_sha256,
            "all-TU report does not describe this generated corpus")
    require(
        all_tus["inputs"]["complete_generated_tree_sha256"] ==
        EXPECTED_GENERATED_TREE_SHA256,
        "generated tree hash changed",
    )

    mapping_text = mapping_path.read_text(encoding="utf-8")
    mapping_rows = MAPPING.findall(mapping_text)
    require(len(mapping_rows) == EXPECTED_MAPPING_COUNT,
            "function mapping count changed")
    require(len({address for address, _ in mapping_rows}) == len(mapping_rows),
            "duplicate guest address in function mapping")
    require(len({symbol for _, symbol in mapping_rows}) == len(mapping_rows),
            "duplicate symbol in function mapping")

    calls, indirect_sites, origins, bodies = parse_generated(numbered_sources)
    generated = set(calls)
    require(ENTRY in generated, "title entry implementation is missing")
    require(BOUNDARIES <= generated, "entry boundary implementation is missing")
    require(origins[ENTRY] == ("ppc_recomp.216.cpp", "__imp___xstart"),
            "entry implementation origin changed")

    xex_report = json.loads(xex_report_path.read_text(encoding="utf-8"))
    import_items = xex_report["imports"]["items"]
    callable_items = [item for item in import_items
                      if item["thunk_address"] is not None]
    data_items = [item for item in import_items
                  if item["thunk_address"] is None]
    require(len(import_items) == 347 and len(callable_items) == 334
            and len(data_items) == 13, "XEX import surface changed")
    callable_by_symbol = {
        "__imp__" + str(item["name"]): item for item in callable_items
    }
    callable_imports = set(callable_by_symbol)
    require(len(callable_imports) == len(callable_items),
            "duplicate callable import symbol")
    mapping_symbols = {symbol for _, symbol in mapping_rows}
    require(mapping_symbols == generated | callable_imports,
            "mapping symbols differ from generated functions plus imports")

    all_sites = [(caller, callee) for caller in generated
                 for callee in calls[caller]]
    all_edges = set(all_sites)
    generated_edges = {(a, b) for a, b in all_edges if b in generated}
    import_edges = {(a, b) for a, b in all_edges if b in callable_imports}
    unclassified_edges = all_edges - generated_edges - import_edges
    require(not unclassified_edges, "global direct graph has unknown callees")
    require(len(all_sites) == EXPECTED_DIRECT_CALL_SITE_COUNT,
            "direct call-site count changed")
    require(len(all_edges) == EXPECTED_UNIQUE_DIRECT_EDGE_COUNT,
            "unique direct-edge count changed")
    require(sum(indirect_sites.values()) == EXPECTED_INDIRECT_CALL_SITE_COUNT,
            "indirect dispatch-site count changed")

    full, full_generated, full_imports = closure_summary(
        calls, indirect_sites, callable_imports, set()
    )
    narrowed, narrowed_generated, narrowed_imports = closure_summary(
        calls, indirect_sites, callable_imports, BOUNDARIES
    )
    require((len(full_generated), len(full_imports)) == (6766, 151),
            "full entry closure changed")
    require((len(narrowed_generated), len(narrowed_imports)) == (76, 27),
            "boundary-stopped entry closure changed")
    require(full["total_nodes_including_imports"] == 6917,
            "full entry total node count changed")
    require(narrowed["total_nodes_including_imports"] == 103,
            "boundary-stopped total node count changed")

    active_narrowed = narrowed_generated - BOUNDARIES
    frontier_items: list[dict[str, Any]] = []
    for symbol in sorted(narrowed_imports):
        item = callable_by_symbol[symbol]
        callsite_count = sum(
            callee == symbol for caller in active_narrowed
            for callee in calls[caller]
        )
        callers = sorted({
            caller for caller in active_narrowed if symbol in calls[caller]
        })
        frontier_items.append({
            "symbol": symbol,
            "name": item["name"],
            "library": item["library"],
            "library_version": item["library_version"],
            "ordinal": item["ordinal"],
            "reference_address": item["reference_address"],
            "thunk_address": item["thunk_address"],
            "static_call_sites_in_boundary_stopped_closure": callsite_count,
            "distinct_callers_in_boundary_stopped_closure": len(callers),
            "callers": callers,
        })

    library_symbols = Counter(row["library"] for row in frontier_items)
    library_sites = Counter()
    for row in frontier_items:
        library_sites[str(row["library"])] += int(
            row["static_call_sites_in_boundary_stopped_closure"]
        )

    direct_sequence = xstart_sequence(
        bodies[ENTRY], generated, callable_imports
    )
    expected_sequence = [
        "__savegprlr_28", "sub_84BF1950", "sub_84BF0C50",
        "sub_84BE9B20", "__imp__XamLoaderTerminateTitle",
        "sub_84BDEA98", "sub_84BF17D8", "sub_84BF16F8",
        "sub_84BF1620", TITLE_MAIN, POST_MAIN, "__imp__DbgPrint",
        "__imp__XamLoaderTerminateTitle",
    ]
    require([row["callee"] for row in direct_sequence] == expected_sequence,
            "direct entry call order changed")

    report = {
        "schema": SCHEMA,
        "result": {
            "entry_symbol": ENTRY,
            "entry_guest_address": "0x84BE9D08",
            "generated_implementation_count": len(generated),
            "mapping_count": len(mapping_rows),
            "global_direct_call_site_count": len(all_sites),
            "global_unique_direct_edge_count": len(all_edges),
            "global_indirect_dispatch_site_count": sum(indirect_sites.values()),
            "full_entry_direct_closure_total_nodes": (
                full["total_nodes_including_imports"]
            ),
            "full_entry_reachable_callable_imports": len(full_imports),
            "boundary_stopped_total_nodes": (
                narrowed["total_nodes_including_imports"]
            ),
            "boundary_stopped_callable_imports": len(narrowed_imports),
            "callable_import_semantics_implemented": False,
            "indirect_targets_resolved": False,
            "successful_boot_path_proved": False,
            "title_entry_executed": False,
        },
        "inputs": {
            "generated_directory": relative(generated_dir, root),
            "numbered_source_count": len(numbered_sources),
            "generated_cpp_manifest_sha256": manifest_sha256,
            "complete_generated_tree_sha256": EXPECTED_GENERATED_TREE_SHA256,
            "mapping_source": {
                "path": relative(mapping_path, root),
                "size": mapping_path.stat().st_size,
                "sha256": sha256_file(mapping_path),
            },
            "xex_report": {
                "path": relative(xex_report_path, root),
                "size": xex_report_path.stat().st_size,
                "sha256": sha256_file(xex_report_path),
            },
            "all_tus_report": {
                "path": relative(all_tus_path, root),
                "size": all_tus_path.stat().st_size,
                "sha256": sha256_file(all_tus_path),
            },
        },
        "import_surface": {
            "logical_imports": len(import_items),
            "callable_thunks": len(callable_items),
            "imported_data_slots": len(data_items),
            "callable_thunks_with_any_global_static_call": len({
                callee for _, callee in import_edges
            }),
            "global_callable_import_call_sites": sum(
                callee in callable_imports for _, callee in all_sites
            ),
            "global_unique_callable_import_edges": len(import_edges),
            "data_slots_participate_in_direct_call_graph": False,
        },
        "global_direct_graph": {
            "generated_nodes": len(generated),
            "direct_call_sites": len(all_sites),
            "unique_direct_edges": len(all_edges),
            "generated_call_sites": sum(
                callee in generated for _, callee in all_sites
            ),
            "unique_generated_edges": len(generated_edges),
            "callable_import_call_sites": sum(
                callee in callable_imports for _, callee in all_sites
            ),
            "unique_callable_import_edges": len(import_edges),
            "unclassified_direct_edges": 0,
            "indirect_dispatch_sites": sum(indirect_sites.values()),
        },
        "full_entry_direct_closure": {
            **full,
            "reachable_callable_imports": sorted(full_imports),
            "interpretation": (
                "Syntactic direct-call closure from _xstart with no opaque "
                "boundary; branches are not path-filtered and indirect "
                "targets are omitted."
            ),
        },
        "boundary_stopped_entry_closure": {
            "entry": ENTRY,
            "opaque_boundaries": [
                {"symbol": TITLE_MAIN, "role": "title_main"},
                {"symbol": POST_MAIN, "role": "post_main_teardown"},
            ],
            **narrowed,
            "callable_imports_by_library": dict(sorted(library_symbols.items())),
            "static_import_call_sites_by_library": dict(
                sorted(library_sites.items())
            ),
            "frontier": frontier_items,
            "interpretation": (
                "Both boundary nodes count as reached but their bodies are "
                "not traversed. Calls elsewhere in _xstart, including "
                "conditional failure and syntactically post-main calls, "
                "remain included because this is not path-sensitive."
            ),
        },
        "entry_direct_call_sequence": {
            "implementation_source": origins[ENTRY][0],
            "internal_implementation_symbol": origins[ENTRY][1],
            "site_count": len(direct_sequence),
            "calls_in_source_order": direct_sequence,
            "execution_order_proved": False,
            "note": (
                "Source order is exact; conditions, early termination, and "
                "callee return behavior are deliberately not inferred."
            ),
        },
        "method_and_limits": {
            "alias_normalization": (
                "Every PPC_FUNC_IMPL internal __imp__ prefix is removed only "
                "after its public PPC_WEAK_FUNC alias is verified."
            ),
            "direct_edge_rule": (
                "A direct edge is an exact generated statement of the form "
                "callee(ctx, base); inside a PPC_FUNC_IMPL body."
            ),
            "path_sensitivity": False,
            "failure_and_destructor_paths_filtered": False,
            "indirect_dispatch_target_inference": False,
            "why_overapproximate": (
                "All syntactic branch arms and after-main entry-shell calls "
                "are included even when a successful run may not take them."
            ),
            "why_incomplete": (
                "Fifteen PPC_CALL_INDIRECT_FUNC sites remain in the narrowed "
                "descended graph, and imported data, callbacks, virtual "
                "dispatch, exception flow, and runtime-created targets are "
                "outside this direct-call closure."
            ),
        },
        "portme": [
            (
                "PORTME: classify happy-path versus failure/destructor-only "
                "imports with validated guest control-flow and runtime traces."
            ),
            (
                "PORTME: resolve the 15 indirect dispatch sites in the 74 "
                "descended boundary-stopped functions before calling the "
                "27-symbol set complete."
            ),
            (
                "PORTME: implement guest-ABI-correct semantics for reached "
                "callable imports and separately seed all 13 imported data "
                "slots; names and counts are not implementations."
            ),
            (
                "PORTME at 0x84BE9D08: create a valid PPCContext, guest stack, "
                "TLS/thread state, scheduler, exception policy, and address "
                "ownership before executing _xstart."
            ),
        ],
    }

    output = args.json if args.json.is_absolute() else root / args.json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
