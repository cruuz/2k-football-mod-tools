#!/usr/bin/env python3
"""Audit one APF XenonRecomp corpus containing both candidate families.

The validator supplies a corpus regenerated in an isolated Storage directory
after applying the opcode candidate and switch-tail candidate, in that order,
to a disposable XenonRecomp clone.  This tool pins every source candidate,
checks the generated corpus and first-entry intersection, syntax-compiles and
object-compiles all 237 C++ translation units, and links only a mapping-count
harness behind fail-fast import definitions.  It never calls title entry.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any


SCHEMA = "apf2k8_static_recomp_opcode_switch_composed/v1"
EXPECTED_VENDOR_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
EXPECTED_FILE_COUNT = 240
EXPECTED_CPP_COUNT = 237
EXPECTED_NUMBERED_COUNT = 236
EXPECTED_IMPLEMENTATION_COUNT = 60397
EXPECTED_MAPPING_COUNT = 60731
EXPECTED_TREE_SHA256 = (
    "33bd100b5a7b358dd651b4c55ace6b41c73f9d3552a6684cede299ae9ac9532f"
)
EXPECTED_CPP_MANIFEST_SHA256 = (
    "216e11b389a0da0c808bf7a7f598cf9210e481f90477a73eacb15ea37d120079"
)
EXPECTED_TOTAL_BYTES = 130724396
EXPECTED_CPP_BYTES = 128810039
EXPECTED_LOG_SHA256 = (
    "8819d1f307021bf219ac1e3f32890f8e0626444459189e732f7d10b150979916"
)
EXPECTED_PATCHED_RECOMPILER_SHA256 = (
    "fc7cf1c7c322589085cdab2bb9dd3e15909ff3c08e6ba4af23af3e293f8dfd3e"
)
EXPECTED_PATCHED_CONTEXT_SHA256 = (
    "0c217483f60a4c70d15de1a2ac3a652bf753fc183c2deef4f04b1f8a4727ba52"
)
EXPECTED_GENERATED_CONTEXT_SHA256 = (
    "b3d2b8e5d72997ffd920929d5ca3e2b9863a2b16fabfb4fa3680b9d25009d636"
)
EXPECTED_MAPPING_SHA256 = (
    "9050c9a14781b40e0329ed9abca512f780cfba6ca709c8e8326397a66de6b5bd"
)
EXPECTED_CLANG_SHA256 = (
    "8ef402d453d1ba4902e4ee0f0f847f6cfa01400c95aa43c24e97818b9c0e3f45"
)
EXPECTED_LLD_SHA256 = (
    "7ad9a0e8fe6d0e79b71172d731e33872c0274e49fceb7b516d774876d5a58ade"
)

SOURCE_PINS = {
    "extracted/All-Pro Football 2K8 (USA)/default.xex":
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
    "extracted/All-Pro Football 2K8 (USA)/0A":
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "tools/vendor/XenonRecomp/XenonRecomp/recompiler.cpp":
        "30e7ea5b4d8a225bc3e0ac71aebd1a0af7bcde5aaf5679517719b559c9cd777a",
    "tools/vendor/XenonRecomp/XenonUtils/ppc_context.h":
        "369acaf639c52bb25ee8a2c6a555c7875912f0692b1e8220ea8dab0384e42263",
    "reports/static_recomp/apf2k8_opcode_candidates_composed.patch":
        "5a6f15ebb3ff6c0ae2735e370b04e93033cd6d493be0a7a2697379d63e6f26bd",
    "reports/static_recomp/apf2k8_switch_tail_dispatch_candidate.patch":
        "50bd52395e1510dfee9b33fedf6f65b1bc6583fa4266cf1150d15530431b7007",
    "reports/static_recomp/apf2k8_xenon_switch_tables_switch_tail_candidate.toml":
        "07de9ad5d78cf363449291ed37d5a312c6245816ac0d3ae3a0754c961deeb759",
    "reports/static_recomp/apf2k8_xenonrecomp_opcode_switch_composed.toml":
        "dfd0cbc750bf3f6560e3a3e3002065b94715fba845ac92808789d6b9a8978423",
    "reports/static_recomp/apf2k8_opcode_candidates_composed.json":
        "945c2ee4cf3f56840fe7a83aad8458b36d0cca813761c05b55c152239476917c",
    "reports/static_recomp/apf2k8_static_recomp_switch_tail_dispatch.json":
        "a2ac4ceba673f4ff826cbfa10a5107793b9bdf960035a425c79b0451e2e5ffe5",
    "reports/static_recomp/apf2k8_static_recomp_switch_tail_residue.tsv":
        "42698f9dc3d5a03079a4e8dd6e0fc55060a87eabc2f3176a92c15156a31dbcb0",
    "reports/static_recomp/apf2k8_opcode_gap_sites.tsv":
        "29ba6fc510492cfa58d63b28b5cea606455841b3d3fbe14fd70b883e78e7903b",
    "reports/static_recomp/apf2k8_boot_indirect_frontier.json":
        "01de432fa00e223af4f60e65727d6e35548c6c3e90352e73015fc1c09134cdf7",
    "reports/headers/apf2k8_xex_report.json":
        "dfd21f9db2fdb683b2dbd0390d351fdac84ba1e796a0e0c5e0e60c28827f3f1c",
    "tools/apf_static_boot_import_frontier.py":
        "f6ee5dfba5f840956d9b03a2216ed71406833d2ad20e80cfd1b8a36ce1af0f99",
}

EXPECTED_MNEMONIC_COUNTS = {
    "dcbst": 1,
    "frsqrte": 28,
    "mulhdu": 5,
    "stfsu": 8,
    "vaddsws": 6,
    "vandc": 16,
    "vpkswss": 51,
    "vrfip": 1,
    "vsel128": 54,
    "vsrab": 1,
    "vsubuwm": 1,
}

IMPLEMENTATION = re.compile(r"^PPC_FUNC_IMPL\(([^)]+)\)", re.MULTILINE)
MAPPING = re.compile(
    r"^\s*\{\s*0x([0-9A-F]+),\s*([A-Za-z_][A-Za-z0-9_]*)\s*\},$",
    re.MULTILINE,
)
SWITCH_ERROR = re.compile(
    r"^ERROR: Switch case at ([0-9A-F]+) is trying to jump outside "
    r"function: ([0-9A-F]+)$"
)
UNRESOLVED = re.compile(
    r"PORTME: unresolved cross-function switch target "
    r"(0x[0-9A-F]+) from bctr (0x[0-9A-F]+)"
)
RESOLVED = re.compile(
    r"CROSS_FUNCTION_SWITCH_TAIL: exact mapped target (0x[0-9A-F]+)"
)
SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CorpusError(RuntimeError):
    """Raised when a source pin or derived-corpus invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CorpusError(message)


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path, logical: str) -> dict[str, Any]:
    return {
        "path": logical,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def expected_cpp_names() -> list[str]:
    return ["ppc_func_mapping.cpp", *[
        f"ppc_recomp.{index}.cpp" for index in range(EXPECTED_NUMBERED_COUNT)
    ]]


def expected_all_names() -> list[str]:
    return sorted([
        "ppc_config.h", "ppc_context.h", "ppc_recomp_shared.h",
        *expected_cpp_names(),
    ])


def manifest(directory: Path) -> tuple[list[dict[str, Any]], str, int]:
    rows: list[dict[str, Any]] = []
    state = hashlib.sha256()
    total = 0
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        size = path.stat().st_size
        digest = sha256_file(path)
        rows.append({"name": path.name, "size": size, "sha256": digest})
        state.update(path.name.encode("utf-8") + b"\0")
        state.update(size.to_bytes(8, "big"))
        state.update(bytes.fromhex(digest))
        total += size
    return rows, state.hexdigest(), total


def cpp_manifest(directory: Path) -> tuple[list[dict[str, Any]], str, int]:
    rows: list[dict[str, Any]] = []
    state = hashlib.sha256()
    total = 0
    for name in expected_cpp_names():
        path = directory / name
        size = path.stat().st_size
        digest = sha256_file(path)
        rows.append({"name": name, "size": size, "sha256": digest})
        state.update(name.encode("utf-8") + b"\0")
        state.update(size.to_bytes(8, "big"))
        state.update(bytes.fromhex(digest))
        total += size
    return rows, state.hexdigest(), total


def load_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("apf_frontier", path)
    require(spec is not None and spec.loader is not None,
            "cannot load frontier parser")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_owner(internal: str) -> str:
    require(internal.startswith("__imp__"),
            f"generated owner lacks __imp__ prefix: {internal}")
    return internal[len("__imp__"):]


def switch_blocks(numbered: list[Path]) -> tuple[
    list[tuple[str, str, str]], list[tuple[str, str]]
]:
    unresolved: list[tuple[str, str, str]] = []
    resolved: list[tuple[str, str]] = []
    for source in numbered:
        owner: str | None = None
        for line in source.read_text(encoding="utf-8").splitlines():
            if match := IMPLEMENTATION.match(line):
                owner = normalize_owner(match.group(1))
            if match := UNRESOLVED.search(line):
                require(owner is not None, "unresolved switch lacks owner")
                unresolved.append((owner, match.group(1), match.group(2)))
            if match := RESOLVED.search(line):
                require(owner is not None, "resolved switch lacks owner")
                resolved.append((owner, match.group(1)))
    return unresolved, resolved


def first_entry_intersection(
    root: Path, numbered: list[Path], unresolved: list[tuple[str, str, str]],
    resolved: list[tuple[str, str]],
) -> dict[str, Any]:
    frontier_path = root / "tools/apf_static_boot_import_frontier.py"
    frontier = load_module(frontier_path)
    calls, _, _, _ = frontier.parse_generated(numbered)
    xex = json.loads((root / "reports/headers/apf2k8_xex_report.json").read_text(
        encoding="utf-8"))
    callable_imports = {
        "__imp__" + item["name"] for item in xex["imports"]["items"]
        if item["thunk_address"] is not None
    }
    indirect = json.loads((
        root / "reports/static_recomp/apf2k8_boot_indirect_frontier.json"
    ).read_text(encoding="utf-8"))
    proved: dict[str, set[str]] = defaultdict(set)
    for site in indirect["original_indirect_sites"]:
        for target in site["proved_targets"]:
            proved[site["caller"]].add(target["symbol"])

    reached: set[str] = set()
    reached_imports: set[str] = set()
    pending: deque[str] = deque([frontier.ENTRY])
    while pending:
        caller = pending.popleft()
        if caller in reached:
            continue
        require(caller in calls, f"first-entry body missing: {caller}")
        reached.add(caller)
        if caller in frontier.BOUNDARIES:
            continue
        for callee in set(calls[caller]) | proved.get(caller, set()):
            if callee in calls:
                pending.append(callee)
            elif callee in callable_imports:
                reached_imports.add(callee)
            else:
                raise CorpusError(f"unclassified first-entry edge: {callee}")
    active = reached - frontier.BOUNDARIES
    require((len(reached), len(active), len(reached_imports)) == (428, 426, 30),
            "augmented first-entry frontier changed")

    opcode_rows = list(csv.DictReader((
        root / "reports/static_recomp/apf2k8_opcode_gap_sites.tsv"
    ).open(encoding="utf-8"), delimiter="\t"))
    require(len(opcode_rows) == 172, "opcode candidate site ledger changed")
    opcode_owners = {
        "sub_" + row["function_start"][2:].upper() for row in opcode_rows
    }
    preboundary = {
        "_xstart", "__savegprlr_28", "sub_84BF1950", "sub_84BF1850"
    }
    return {
        "augmented_generated_nodes_including_boundaries": len(reached),
        "augmented_descended_generated_nodes": len(active),
        "frontier_callable_imports": len(reached_imports),
        "global_opcode_candidate_sites": len(opcode_rows),
        "opcode_candidate_sites_in_frontier": sum(
            ("sub_" + row["function_start"][2:].upper()) in active
            for row in opcode_rows
        ),
        "opcode_candidate_owners_in_frontier": len(opcode_owners & active),
        "unresolved_switch_occurrences_in_frontier": sum(
            owner in active for owner, _, _ in unresolved
        ),
        "resolved_switch_tail_occurrences_in_frontier": sum(
            owner in active for owner, _ in resolved
        ),
        "candidate_occurrences_in_preboundary_symbols": sum(
            owner in preboundary for owner, _, _ in unresolved
        ) + sum(owner in preboundary for owner, _ in resolved) + sum(
            ("sub_" + row["function_start"][2:].upper()) in preboundary
            for row in opcode_rows
        ),
        "entry_symbol": frontier.ENTRY,
        "entry_called": False,
    }


def compile_one(command: list[str], name: str, output: Path | None) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "name": name,
        "return_code": completed.returncode,
        "stdout_empty": completed.stdout == "",
        "stderr_empty": completed.stderr == "",
        "object_created": output.is_file() if output is not None else None,
    }


def run_parallel(
    specs: list[tuple[list[str], str, Path | None]], jobs: int
) -> list[dict[str, Any]]:
    outcomes: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(compile_one, command, name, output): name
            for command, name, output in specs
        }
        for future in as_completed(futures):
            result = future.result()
            outcomes[str(result["name"])] = result
    return [outcomes[name] for _, name, _ in specs]


def import_stub_source(names: list[str]) -> str:
    parts = [
        '#include "ppc_recomp_shared.h"\n',
        "#include <cstdlib>\n\n",
        "[[noreturn]] static void apf_portme_import_trap() { std::abort(); }\n\n",
        "// PORTME: replace each fail-fast definition with recovered guest-ABI semantics.\n",
        "#define APF_PORTME_IMPORT(symbol) PPC_FUNC(symbol) { (void)ctx; (void)base; apf_portme_import_trap(); }\n\n",
    ]
    parts.extend(f"APF_PORTME_IMPORT({name})\n" for name in names)
    parts.append("\n#undef APF_PORTME_IMPORT\n")
    return "".join(parts)


def harness_source() -> str:
    return """#include \"ppc_recomp_shared.h\"
#include <cstddef>

int main() {
    std::size_t count = 0;
    while (PPCFuncMappings[count].host != nullptr) {
        ++count;
    }
    return count == 60731 ? 0 : 1;
}
"""


def compile_and_link(
    root: Path, generated: Path, compiler: str, linker: str,
    jobs: int, temp_root: Path,
) -> dict[str, Any]:
    sources = [generated / name for name in expected_cpp_names()]
    includes = [
        generated,
        root / "tools/vendor/XenonRecomp/XenonUtils",
        root / "tools/vendor/XenonRecomp/thirdparty/simde",
    ]
    syntax_specs: list[tuple[list[str], str, Path | None]] = []
    for source in sources:
        command = [compiler, "-std=c++20", "-O0", "-fsyntax-only"]
        command.extend(f"-I{path}" for path in includes)
        command.append(str(source))
        syntax_specs.append((command, source.name, None))
    syntax = run_parallel(syntax_specs, jobs)
    require(len(syntax) == EXPECTED_CPP_COUNT, "syntax roster changed")
    require(all(row["return_code"] == 0 and row["stdout_empty"] and
                row["stderr_empty"] for row in syntax),
            "all-TU syntax audit failed")

    xex = json.loads((root / "reports/headers/apf2k8_xex_report.json").read_text(
        encoding="utf-8"))
    import_names = [
        "__imp__" + item["name"] for item in xex["imports"]["items"]
        if item["thunk_address"] is not None
    ]
    require(len(import_names) == len(set(import_names)) == 334 and
            all(SYMBOL.fullmatch(name) for name in import_names),
            "callable import surface changed")
    data_imports = [
        item for item in xex["imports"]["items"]
        if item["thunk_address"] is None
    ]
    require(len(data_imports) == 13, "imported-data surface changed")
    stubs_text = import_stub_source(import_names)
    harness_text = harness_source()
    require("_xstart(" not in stubs_text and "_xstart(" not in harness_text,
            "title-entry call leaked into link support")

    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apf-composed-link-",
                                     dir=temp_root) as temporary:
        build = Path(temporary)
        stubs = build / "failfast_imports.cpp"
        harness = build / "mapping_harness.cpp"
        stubs.write_text(stubs_text, encoding="utf-8")
        harness.write_text(harness_text, encoding="utf-8")
        all_sources = [*sources, stubs, harness]
        object_specs: list[tuple[list[str], str, Path | None]] = []
        objects: list[Path] = []
        for index, source in enumerate(all_sources):
            output = build / f"{index:03d}.o"
            command = [compiler, "-std=c++20", "-O0", "-c", str(source),
                       "-o", str(output)]
            command.extend(f"-I{path}" for path in includes)
            object_specs.append((command, source.name, output))
            objects.append(output)
        object_outcomes = run_parallel(object_specs, jobs)
        require(len(object_outcomes) == 239, "object roster changed")
        require(all(row["return_code"] == 0 and row["stdout_empty"] and
                    row["stderr_empty"] and row["object_created"]
                    for row in object_outcomes),
                "object compilation failed")

        executable = build / "mapping-link-probe"
        linked = subprocess.run([
            compiler, "-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie",
            *map(str, objects), "-lm", "-o", str(executable),
        ], capture_output=True, text=True, check=False)
        require(linked.returncode == 0 and linked.stdout == "" and
                linked.stderr == "", "mapping-only link failed: " +
                linked.stderr[-2000:])
        executed = subprocess.run([str(executable)], capture_output=True,
                                  text=True, check=False, timeout=60)
        require(executed.returncode == 0 and executed.stdout == "" and
                executed.stderr == "", "mapping-only harness failed")
        undefined = subprocess.run(
            ["nm", "-u", str(executable)], capture_output=True,
            text=True, check=True).stdout.splitlines()
        unresolved_guest = [
            line for line in undefined
            if "__imp__" in line or re.search(r"\bsub_[0-9A-F]+", line)
        ]
        require(not unresolved_guest, "linked probe retains guest symbols")
        defined = subprocess.run(
            ["nm", "-C", "--defined-only", str(executable)],
            capture_output=True, text=True, check=True).stdout
        defined_imports = sum(
            f" {name}(PPCContext&, unsigned char*)" in defined
            for name in import_names
        )
        require(defined_imports == 334,
                "not all fail-fast import definitions linked")

    return {
        "syntax": {
            "translation_unit_count": len(syntax),
            "passed_count": sum(row["return_code"] == 0 for row in syntax),
            "failed_count": sum(row["return_code"] != 0 for row in syntax),
            "diagnostic_translation_unit_count": sum(
                not row["stdout_empty"] or not row["stderr_empty"]
                for row in syntax
            ),
            "flags": ["-std=c++20", "-O0", "-fsyntax-only"],
            "outcomes": syntax,
        },
        "object_build": {
            "generated_object_count": EXPECTED_CPP_COUNT,
            "support_object_count": 2,
            "compiled_object_count": len(object_outcomes),
            "failed_count": sum(
                row["return_code"] != 0 for row in object_outcomes
            ),
            "diagnostic_object_count": sum(
                not row["stdout_empty"] or not row["stderr_empty"]
                for row in object_outcomes
            ),
            "flags": ["-std=c++20", "-O0", "-c"],
            "outcomes": object_outcomes,
        },
        "link": {
            "link_succeeded": True,
            "mapping_only_harness_return_code": 0,
            "mapping_count_checked": EXPECTED_MAPPING_COUNT,
            "undefined_guest_symbol_count": 0,
            "fail_fast_callable_import_definitions": defined_imports,
            "imported_data_slots_not_satisfied_by_link": len(data_imports),
            "host_libraries": ["libm"],
            "temporary_executable_preserved": False,
            "title_entry_called": False,
            "translated_title_code_executed": False,
        },
        "support_source": {
            "fail_fast_import_source_sha256": sha256_bytes(
                stubs_text.encode("utf-8")),
            "mapping_harness_source_sha256": sha256_bytes(
                harness_text.encode("utf-8")),
            "source_embedded_in_report": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--logical-generated", default=(
        "build-static-recomp-apf/ppc-opcode-switch-composed"))
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--patched-recompiler", type=Path, required=True)
    parser.add_argument("--patched-context", type=Path, required=True)
    parser.add_argument("--temp-root", type=Path, default=Path(
        "/media/noah/Storage/.codex-tmp"))
    parser.add_argument("--clang", default="clang++-18")
    parser.add_argument("--jobs", type=int,
                        default=max(1, min(12, os.cpu_count() or 1)))
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    resolve = lambda path: path.resolve() if path.is_absolute() else \
        (root / path).resolve()
    generated = resolve(args.generated)
    log_path = resolve(args.log)
    patched_recompiler = resolve(args.patched_recompiler)
    patched_context = resolve(args.patched_context)
    temp_root = resolve(args.temp_root)
    output = resolve(args.json)
    require(args.jobs > 0 and generated.is_dir() and log_path.is_file(),
            "generated corpus, log, or positive job count is missing")

    source_pins: dict[str, dict[str, Any]] = {}
    for logical, expected in SOURCE_PINS.items():
        path = root / logical
        require(path.is_file() and sha256_file(path) == expected,
                f"source candidate changed: {logical}")
        source_pins[logical] = pin(path, logical)
    vendor = root / "tools/vendor/XenonRecomp"
    commit = subprocess.run(
        ["git", "-C", str(vendor), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    require(commit == EXPECTED_VENDOR_COMMIT, "vendor commit changed")
    for command in (("diff", "--quiet", "HEAD", "--"),
                    ("diff", "--cached", "--quiet", "HEAD", "--")):
        require(subprocess.run(
            ["git", "-C", str(vendor), *command], check=False
        ).returncode == 0, "pinned vendor tree is dirty")
    require(sha256_file(patched_recompiler) ==
            EXPECTED_PATCHED_RECOMPILER_SHA256,
            "sequentially patched recompiler hash changed")
    require(sha256_file(patched_context) == EXPECTED_PATCHED_CONTEXT_SHA256,
            "sequentially patched context hash changed")

    all_rows, tree_digest, total_bytes = manifest(generated)
    require([row["name"] for row in all_rows] == expected_all_names(),
            "generated file roster changed")
    require((len(all_rows), total_bytes, tree_digest) == (
        EXPECTED_FILE_COUNT, EXPECTED_TOTAL_BYTES, EXPECTED_TREE_SHA256),
        "complete generated corpus changed")
    cpp_rows, cpp_digest, cpp_bytes = cpp_manifest(generated)
    require((len(cpp_rows), cpp_bytes, cpp_digest) == (
        EXPECTED_CPP_COUNT, EXPECTED_CPP_BYTES,
        EXPECTED_CPP_MANIFEST_SHA256), "generated C++ manifest changed")
    require(sha256_file(generated / "ppc_context.h") ==
            EXPECTED_GENERATED_CONTEXT_SHA256,
            "generated patched context changed")
    require(sha256_file(generated / "ppc_func_mapping.cpp") ==
            EXPECTED_MAPPING_SHA256, "mapping source changed")

    log_lines = log_path.read_text(encoding="utf-8").splitlines()
    require(sha256_file(log_path) == EXPECTED_LOG_SHA256,
            "combined regeneration log changed")
    require(log_lines and log_lines[-1] == "Recompiling functions... 100%",
            "combined regeneration did not reach 100%")
    require(not any(line.startswith("Unrecognized instruction")
                    for line in log_lines),
            "combined corpus retained an unrecognized instruction")
    switch_errors = [
        match.groups() for line in log_lines
        if (match := SWITCH_ERROR.match(line))
    ]
    require(len(switch_errors) == 1076 and
            len({target for _, target in switch_errors}) == 190,
            "combined switch residue log changed")

    numbered = [
        generated / f"ppc_recomp.{index}.cpp"
        for index in range(EXPECTED_NUMBERED_COUNT)
    ]
    generated_text = "".join(
        path.read_text(encoding="utf-8") for path in numbered
    )
    implementation_count = sum(
        len(IMPLEMENTATION.findall(path.read_text(encoding="utf-8")))
        for path in numbered
    )
    mapping_count = len(MAPPING.findall((
        generated / "ppc_func_mapping.cpp"
    ).read_text(encoding="utf-8")))
    require((implementation_count, mapping_count) == (
        EXPECTED_IMPLEMENTATION_COUNT, EXPECTED_MAPPING_COUNT),
        "generated function topology changed")
    mnemonic_counts = {
        mnemonic: len(re.findall(
            rf"^\s*// {mnemonic}(?:\s|$)", generated_text, re.MULTILINE))
        for mnemonic in EXPECTED_MNEMONIC_COUNTS
    }
    require(mnemonic_counts == EXPECTED_MNEMONIC_COUNTS,
            "composed opcode coverage changed")
    require(len(re.findall(
        r"^\s*ctx\.f\d+\.u64 = PPC_FRSQRTE_XENIA_6E5B832_VALUE\(",
        generated_text, re.MULTILINE)) == 28,
        "frsqrte candidate helper coverage changed")
    require(len(re.findall(
        r"^\s*PPC_DATA_CACHE_BLOCK_STORE\(", generated_text,
        re.MULTILINE)) == 1 and
        generated_text.count("// PORTME(0x84B46518):") == 1,
        "dcbst candidate coverage changed")
    unresolved, resolved = switch_blocks(numbered)
    require(len(unresolved) == 1076 and
            len({target for _, target, _ in unresolved}) == 190 and
            len(resolved) == 2261 and "// ERROR:" not in generated_text,
            "composed switch-tail blocks changed")

    switch_candidate = root / "build-static-recomp-apf/ppc-switch-tail-candidate"
    require(switch_candidate.is_dir(), "validated switch candidate is missing")
    switch_numbered = [
        switch_candidate / f"ppc_recomp.{index}.cpp"
        for index in range(EXPECTED_NUMBERED_COUNT)
    ]
    switch_unresolved, switch_resolved = switch_blocks(switch_numbered)
    require(Counter(unresolved) == Counter(switch_unresolved) and
            Counter(resolved) == Counter(switch_resolved),
            "combined control-flow blocks differ from validated candidate")
    frontier = first_entry_intersection(
        root, numbered, unresolved, resolved)
    require(frontier["opcode_candidate_sites_in_frontier"] == 0 and
            frontier["unresolved_switch_occurrences_in_frontier"] == 0 and
            frontier["resolved_switch_tail_occurrences_in_frontier"] == 0 and
            frontier["candidate_occurrences_in_preboundary_symbols"] == 0,
            "candidate residue or repair entered first-entry frontier")

    compiler_lookup = shutil.which(args.clang)
    linker_lookup = shutil.which("ld.lld-18")
    require(compiler_lookup is not None and linker_lookup is not None,
            "pinned Clang/LLD toolchain is unavailable")
    # Preserve the clang++ driver name for automatic C++ runtime linkage;
    # hash and report the exact resolved compiler binary independently.
    compiler = compiler_lookup
    compiler_resolved = str(Path(compiler_lookup).resolve())
    linker = str(Path(linker_lookup).resolve())
    require(sha256_file(Path(compiler_resolved)) == EXPECTED_CLANG_SHA256 and
            sha256_file(Path(linker)) == EXPECTED_LLD_SHA256,
            "compiler or linker binary changed")
    compiler_version = subprocess.run(
        [compiler, "--version"], capture_output=True, text=True,
        check=True).stdout.splitlines()[0]
    # lld chooses its GNU-driver personality from argv[0], so retain the
    # ld.lld-18 invocation name for the version probe while hashing the exact
    # resolved binary above.
    linker_version = subprocess.run(
        [linker_lookup, "--version"], capture_output=True, text=True,
        check=True).stdout.strip()
    require(compiler_version == "Ubuntu clang version 18.1.3 (1ubuntu1)" and
            linker_version ==
            "Ubuntu LLD 18.1.3 (compatible with GNU linkers)",
            "compiler or linker version changed")
    build = compile_and_link(
        root, generated, compiler, linker, args.jobs, temp_root)

    report = {
        "schema": SCHEMA,
        "result": {
            "single_composed_derived_corpus_exists": True,
            "opcode_candidate_included": True,
            "switch_tail_candidate_included": True,
            "unrecognized_instruction_count": 0,
            "resolved_switch_tail_occurrences": len(resolved),
            "remaining_switch_portme_occurrences": len(unresolved),
            "remaining_switch_unique_targets": len({
                target for _, target, _ in unresolved
            }),
            "generated_translation_units_syntax_passed": 237,
            "generated_translation_units_object_compiled": 237,
            "mapping_only_link_succeeded": True,
            "composed_derived_corpus_blocker_resolved": True,
            "entry_authorized": False,
            "title_entry_called": False,
            "translated_title_code_executed": False,
            "native_boot_proved": False,
            "architecture_complete": False,
        },
        "composition": {
            "patch_order": [
                "apf2k8_opcode_candidates_composed.patch",
                "apf2k8_switch_tail_dispatch_candidate.patch",
            ],
            "sequentially_patched_recompiler_sha256":
                EXPECTED_PATCHED_RECOMPILER_SHA256,
            "sequentially_patched_context_sha256":
                EXPECTED_PATCHED_CONTEXT_SHA256,
            "recovered_switch_table_sha256": SOURCE_PINS[
                "reports/static_recomp/"
                "apf2k8_xenon_switch_tables_switch_tail_candidate.toml"],
            "pinned_vendor_modified": False,
            "retail_inputs_modified": False,
        },
        "generated_corpus": {
            "path": args.logical_generated,
            "file_count": len(all_rows),
            "cpp_translation_unit_count": len(cpp_rows),
            "numbered_translation_unit_count": EXPECTED_NUMBERED_COUNT,
            "generated_implementation_count": implementation_count,
            "dispatch_mapping_count": mapping_count,
            "total_bytes": total_bytes,
            "cpp_total_bytes": cpp_bytes,
            "tree_sha256": tree_digest,
            "cpp_manifest_sha256": cpp_digest,
            "files": all_rows,
        },
        "regeneration": {
            "completed": True,
            "terminal_log_line": log_lines[-1],
            "log": pin(
                log_path,
                "reports/static_recomp/"
                "apf2k8_xenonrecomp_opcode_switch_composed.log"),
            "unrecognized_instruction_count": 0,
            "switch_error_occurrences": len(switch_errors),
            "switch_error_unique_targets": len({
                target for _, target in switch_errors
            }),
            "title_code_executed": False,
        },
        "candidate_coverage": {
            "opcode_mnemonic_comment_counts": mnemonic_counts,
            "opcode_candidate_site_count": sum(mnemonic_counts.values()),
            "frsqrte_helper_call_count": 28,
            "dcbst_hook_call_count": 1,
            "switch_tail_resolved_occurrences": len(resolved),
            "switch_tail_unresolved_occurrences": len(unresolved),
            "switch_tail_unresolved_unique_targets": len({
                target for _, target, _ in unresolved
            }),
            "switch_blocks_match_validated_switch_only_candidate": True,
        },
        "first_entry_intersection": frontier,
        "compile_and_link_audit": {
            "compiler": {
                "requested": args.clang,
                "resolved_path": compiler_resolved,
                "sha256": EXPECTED_CLANG_SHA256,
                "version": compiler_version,
            },
            "linker": {
                "path": linker,
                "sha256": EXPECTED_LLD_SHA256,
                "version": linker_version,
            },
            "jobs": args.jobs,
            **build,
        },
        "sources": {
            "vendor_commit": commit,
            "source_candidates": source_pins,
            "generator": pin(
                Path(__file__).resolve(),
                "tools/apf_static_recomp_opcode_switch_composed.py"),
            "report_embeds_generated_source_or_title_bytes": False,
        },
        "worked": [
            "One isolated corpus now contains both already-reviewed candidate families.",
            "All 237 generated C++ units pass syntax and object compilation.",
            "All generated symbols link behind 334 explicit fail-fast callable-import definitions.",
            "No opcode or switch candidate occurrence intersects the augmented first-entry frontier.",
        ],
        "failed_or_unproved": [
            "The 1,076 unresolved switch occurrences remain explicit non-executable PORTMEs.",
            "Candidate opcode emission is not architecture-complete Xenon behavior.",
            "The mapping harness does not initialize imported data or execute translated title code.",
            "A composed corpus does not authorize first-entry execution.",
        ],
        "blocking": [
            "Instrument every executed guest instruction against the bounded first-entry ledger.",
            "Resolve the remaining switch residue and opcode semantic caveats before whole-title execution.",
            "Implement guest imports, memory/MMIO, scheduler, filesystem, graphics, and audio behavior.",
        ],
        "portme": [
            "// PORTME: implement sticky VSCR.SAT behavior for all 57 saturating VMX candidate sites.",
            "// PORTME: validate all 28 frsqrte sites on Xenon hardware and implement FPSCR/NI/enabled exceptions.",
            "// PORTME(0x84B46518): implement dcbst protection plus GPU/DMA/MMIO visibility; keep dcbf distinct.",
            "// PORTME: recover every address-specific target in apf2k8_static_recomp_switch_tail_residue.tsv; 1,076 occurrences remain fail-closed.",
            "// PORTME: instrument every generated guest instruction before authorizing any first-entry call.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_STATIC_RECOMP_OPCODE_SWITCH_COMPOSED_PASS "
        "tus=237 syntax=237 objects=237 link=yes opcodes_unrecognized=0 "
        "switch_resolved=2261 switch_remaining=1076 frontier_residue=0 "
        "entry_authorized=0 entry_called=0 title_executed=no"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CorpusError, OSError, ValueError, KeyError,
            subprocess.SubprocessError) as exc:
        raise SystemExit(f"error: {exc}") from exc
