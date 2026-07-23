#!/usr/bin/env python3
"""Object-compile and link the fully instrumented APF corpus without entry.

The temporary harness only counts the generated mapping table.  Every callable
XDK import is a fail-fast definition, and no generated function is invoked.
All objects and the linked executable are deleted before success is reported.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any


EXPECTED_NUMBERED_COUNT = 236
EXPECTED_CPP_COUNT = 237
EXPECTED_HOOK_COUNT = 1_808_124
EXPECTED_IMPORT_COUNT = 334


class LinkProbeError(RuntimeError):
    """Raised when compile/link or a pinned generated invariant fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LinkProbeError(message)


def compile_one(command: list[str], output: Path) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True,
                               check=False)
    return {
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output": output,
    }


def stub_source(import_names: list[str]) -> str:
    lines = [
        '#include "ppc_recomp_shared.h"\n',
        "#include <cstdlib>\n\n",
        "[[noreturn]] static void fail_closed() { std::abort(); }\n",
        "#define APF_IMPORT_STUB(symbol) \\\n    PPC_FUNC(symbol) { (void)ctx; (void)base; fail_closed(); }\n\n",
    ]
    lines.extend(f"APF_IMPORT_STUB({name})\n" for name in import_names)
    lines.append("#undef APF_IMPORT_STUB\n")
    return "".join(lines)


def harness_source() -> str:
    return r'''#include "ppc_recomp_shared.h"

#include <cstddef>
#include <cstdio>

int main() {
    std::size_t mapping_count = 0;
    bool entry_mapping_present = false;
    while (PPCFuncMappings[mapping_count].host != nullptr) {
        if (PPCFuncMappings[mapping_count].guest == 0x84BE9D08u) {
            entry_mapping_present = true;
        }
        ++mapping_count;
        if (mapping_count > 60731u) return 2;
    }
    if (mapping_count != 60731u || !entry_mapping_present) return 3;
    std::printf("APF_INSTRUCTION_BUDGET_LINK_PASS mappings=%zu "
                "generated_cpp=237 hooks=1808124 entry_mapping=1 "
                "entry_called=0\n", mapping_count);
    return 0;
}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--instrumentation-report", type=Path, required=True)
    parser.add_argument("--xex-report", type=Path, default=Path(
        "reports/headers/apf2k8_xex_report.json"))
    parser.add_argument("--clang", default="clang-18")
    parser.add_argument("--clangxx", default="clang++-18")
    parser.add_argument("--jobs", type=int,
                        default=min(16, os.cpu_count() or 1))
    parser.add_argument("--temp-root", type=Path, default=Path(".codex-tmp"))
    parser.add_argument("--transcript", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    resolve = lambda path: path.resolve() if path.is_absolute() else \
        (root / path).resolve()
    generated = resolve(args.generated)
    instrumentation_report = resolve(args.instrumentation_report)
    xex_report = resolve(args.xex_report)
    temp_root = resolve(args.temp_root)
    transcript = resolve(args.transcript)
    clang = shutil.which(args.clang)
    clangxx = shutil.which(args.clangxx)
    require(args.jobs > 0 and clang is not None and clangxx is not None,
            "pinned compilers or positive job count unavailable")
    require(generated.is_dir() and instrumentation_report.is_file() and
            xex_report.is_file(), "link-probe input is missing")

    report = json.loads(instrumentation_report.read_text(encoding="utf-8"))
    result = report["result"]
    require(report["schema"] ==
            "apf2k8_guest_instruction_budget_instrumentation/v1" and
            result["guest_instruction_occurrence_count"] ==
                EXPECTED_HOOK_COUNT and
            result["instrumented_hook_count"] == EXPECTED_HOOK_COUNT and
            result["entry_called"] is False,
            "instrumentation report invariant changed")
    numbered = [generated / f"ppc_recomp.{index}.cpp"
                for index in range(EXPECTED_NUMBERED_COUNT)]
    sources = [generated / "ppc_func_mapping.cpp", *numbered]
    require(len(sources) == EXPECTED_CPP_COUNT and
            all(path.is_file() for path in sources),
            "instrumented generated source roster changed")
    hook_count = sum(path.read_text(encoding="utf-8").count(
        "VC_APF_GUEST_INSTRUCTION_STEP(") for path in numbered)
    require(hook_count == EXPECTED_HOOK_COUNT,
            "instrumented hook count changed before compile")

    xex_data = json.loads(xex_report.read_text(encoding="utf-8"))
    import_names = sorted({
        "__imp__" + item["name"] for item in xex_data["imports"]["items"]
        if item["thunk_address"] is not None
    })
    require(len(import_names) == EXPECTED_IMPORT_COUNT,
            "callable import roster changed")

    include_paths = [
        root / "include",
        generated,
        root / "tools/vendor/XenonRecomp/XenonUtils",
        root / "tools/vendor/XenonRecomp/thirdparty/simde",
    ]
    c_sources = [
        root / "src/static_runtime/apf_first_entry_gate.c",
        root / "src/static_runtime/apf_imported_data_bootstrap.c",
        root / "src/static_runtime/apf_boot_leaf_adapters.c",
    ]
    runtime = root / "src/static_runtime/apf_guest_instruction_budget.cpp"
    require(runtime.is_file() and all(path.is_file() for path in c_sources),
            "budget/ledger runtime source is missing")

    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apf-budget-link-",
                                     dir=temp_root) as temporary:
        build = Path(temporary)
        stubs = build / "imports.cpp"
        harness = build / "mapping_harness.cpp"
        stubs.write_text(stub_source(import_names), encoding="utf-8")
        harness.write_text(harness_source(), encoding="utf-8")
        cpp_sources = [*sources, runtime, stubs, harness]
        compile_specs: list[tuple[list[str], Path]] = []
        for index, source in enumerate(cpp_sources):
            output = build / f"cpp-{index:03d}.o"
            command = [clangxx, "-std=c++20", "-O0", "-c", str(source),
                       "-o", str(output)]
            command.extend(f"-I{path}" for path in include_paths)
            compile_specs.append((command, output))
        for index, source in enumerate(c_sources):
            output = build / f"c-{index:03d}.o"
            command = [clang, "-std=c11", "-O0", "-c", str(source),
                       "-o", str(output), f"-I{root / 'include'}"]
            compile_specs.append((command, output))

        outcomes: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(compile_one, command, output): output
                for command, output in compile_specs
            }
            for future in as_completed(futures):
                outcomes.append(future.result())
        failures = [item for item in outcomes if item["return_code"] != 0]
        require(not failures,
                "object compilation failed: " + " | ".join(
                    item["stderr"][-900:] for item in failures[:3]))
        require(all(item["output"].is_file() for item in outcomes),
                "compiled object is missing")

        executable = build / "apf_instruction_budget_link_probe"
        objects = [output for _, output in compile_specs]
        linked = subprocess.run([
            clangxx, "-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie",
            *map(str, objects), "-o", str(executable),
        ], capture_output=True, text=True, check=False)
        require(linked.returncode == 0,
                "instrumented corpus link failed: " + linked.stderr[-1500:])
        executed = subprocess.run([str(executable)], capture_output=True,
                                  text=True, check=False, timeout=30)
        require(executed.returncode == 0 and executed.stderr == "",
                "mapping-only harness failed: " + executed.stderr[-1000:])
        lines = [line for line in executed.stdout.splitlines()
                 if line.startswith("APF_INSTRUCTION_BUDGET_LINK_PASS ")]
        require(len(lines) == 1 and
                "mappings=60731" in lines[0] and
                "hooks=1808124" in lines[0] and
                "entry_called=0" in lines[0],
                "mapping-only harness transcript changed")
        object_bytes = sum(path.stat().st_size for path in objects)

    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(lines[0] + "\n", encoding="utf-8")
    print(lines[0])
    print(
        "APF_INSTRUCTION_BUDGET_LINK_BUILD_PASS "
        f"objects={len(compile_specs)} object_bytes={object_bytes} "
        f"imports_failfast={len(import_names)} temporary_outputs_deleted=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
