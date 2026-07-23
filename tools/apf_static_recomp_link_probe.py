#!/usr/bin/env python3
"""Compile and link APF's generated C++ against fail-fast import stubs.

The resulting temporary executable only counts the generated function-mapping
table. It never loads retail data or calls title code. Every XEX import stub
aborts if reached, so link success cannot be mistaken for a title runtime.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


SCHEMA = "apf2k8_static_recomp_link_probe/v1"
EXPECTED_TU_COUNT = 237
EXPECTED_NUMBERED_COUNT = 236
EXPECTED_CPP_MANIFEST = "5e90f504e1291e3bcc2ba2e3688da07d44ba7b7bfbf10ac62beffb48d1e79132"
EXPECTED_VENDOR_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LinkProbeError(RuntimeError):
    """Raised when the pinned corpus or compile/link result changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LinkProbeError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "size": path.stat().st_size,
            "sha256": digest_file(path)}


def expected_names() -> list[str]:
    return ["ppc_func_mapping.cpp", *[
        f"ppc_recomp.{index}.cpp" for index in range(EXPECTED_NUMBERED_COUNT)
    ]]


def compile_one(
    compiler: str,
    source: Path,
    output: Path,
    include_paths: list[Path],
) -> dict[str, object]:
    command = [compiler, "-std=c++20", "-O0", "-c", str(source), "-o", str(output)]
    command.extend(f"-I{path}" for path in include_paths)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "name": source.name,
        "return_code": completed.returncode,
        "stdout_empty": completed.stdout == "",
        "stderr_empty": completed.stderr == "",
        "diagnostic_sha256": digest(completed.stderr.encode("utf-8")),
        "object_created": output.is_file(),
        "object_size": output.stat().st_size if output.is_file() else 0,
    }


def stub_source(names: list[str]) -> str:
    lines = [
        '#include "ppc_recomp_shared.h"\n',
        "#include <cstdlib>\n\n",
        "[[noreturn]] static void apf_portme_import_trap() { std::abort(); }\n\n",
        "// Every generated definition below is intentionally fail-fast.\n",
        "// PORTME: replace each with recovered guest-ABI semantics before title execution.\n",
        "#define APF_PORTME_IMPORT(symbol) PPC_FUNC(symbol) { (void)ctx; (void)base; apf_portme_import_trap(); }\n\n",
    ]
    lines.extend(f"APF_PORTME_IMPORT({name})\n" for name in names)
    lines.append("\n#undef APF_PORTME_IMPORT\n")
    return "".join(lines)


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--generated", type=Path,
                        default=Path("build-static-recomp-apf/ppc-filtered"))
    parser.add_argument("--vendor", type=Path,
                        default=Path("tools/vendor/XenonRecomp"))
    parser.add_argument("--xex-report", type=Path,
                        default=Path("reports/headers/apf2k8_xex_report.json"))
    parser.add_argument("--all-tus-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_static_recomp_all_tus.json"))
    parser.add_argument("--clang", default="clang++-18")
    parser.add_argument("--jobs", type=int, default=min(12, os.cpu_count() or 1))
    parser.add_argument("--temp-root", type=Path, default=Path(".codex-tmp"))
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    generated = (root / args.generated).resolve()
    vendor = (root / args.vendor).resolve()
    xex_report_path = (root / args.xex_report).resolve()
    all_tus_path = (root / args.all_tus_report).resolve()
    temp_root = (root / args.temp_root).resolve()
    require(args.jobs > 0, "--jobs must be positive")
    compiler = shutil.which(args.clang)
    require(compiler is not None, f"compiler not found: {args.clang}")
    version = subprocess.run([args.clang, "--version"], capture_output=True,
                             text=True, check=True).stdout.splitlines()[0]
    require("clang version 18.1.3" in version, "pinned Clang version changed")
    linker = shutil.which("ld.lld-18")
    require(linker is not None, "ld.lld-18 is unavailable")
    linker_version = subprocess.run([linker, "--version"], capture_output=True,
                                    text=True, check=True).stdout.strip()

    commit = subprocess.run(["git", "-C", str(vendor), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    require(commit == EXPECTED_VENDOR_COMMIT, "XenonRecomp commit changed")
    all_tus = json.loads(all_tus_path.read_text(encoding="utf-8"))
    require(all_tus["inputs"]["cpp_manifest_sha256"] == EXPECTED_CPP_MANIFEST,
            "generated C++ manifest changed")
    require(all_tus["result"]["all_translation_units_passed"] is True,
            "full syntax prerequisite is not passing")

    names = expected_names()
    sources = [generated / name for name in names]
    require(all(path.is_file() for path in sources), "generated source is missing")
    require(len(list(generated.glob("*.cpp"))) == EXPECTED_TU_COUNT,
            "generated C++ roster changed")

    xex = json.loads(xex_report_path.read_text(encoding="utf-8"))
    callable_items = [item for item in xex["imports"]["items"]
                      if item["thunk_address"] is not None]
    data_items = [item for item in xex["imports"]["items"]
                  if item["thunk_address"] is None]
    import_names = ["__imp__" + item["name"] for item in callable_items]
    require(len(import_names) == 334 and len(set(import_names)) == 334,
            "callable import set changed")
    require(len(data_items) == 13, "data import set changed")
    require(all(SYMBOL.fullmatch(name) for name in import_names),
            "unsafe generated import symbol")

    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apf-link-probe-", dir=temp_root) as tmp:
        build = Path(tmp)
        stubs = build / "apf_portme_import_stubs.cpp"
        harness = build / "apf_link_harness.cpp"
        stub_text = stub_source(import_names)
        harness_text = harness_source()
        stubs.write_text(stub_text, encoding="utf-8")
        harness.write_text(harness_text, encoding="utf-8")
        all_sources = [*sources, stubs, harness]
        objects = [build / f"{index:03d}.o" for index in range(len(all_sources))]
        include_paths = [generated, vendor / "XenonUtils",
                         vendor / "thirdparty/simde"]
        outcomes_by_index: dict[int, dict[str, object]] = {}
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(compile_one, args.clang, source, output,
                                include_paths): index
                for index, (source, output) in enumerate(zip(all_sources, objects))
            }
            for future in as_completed(futures):
                outcomes_by_index[futures[future]] = future.result()
        outcomes = [outcomes_by_index[index] for index in range(len(all_sources))]
        failures = [row for row in outcomes if row["return_code"] != 0]
        require(not failures, f"object compilation failed: {failures[:3]}")
        require(all(row["stderr_empty"] and row["stdout_empty"] for row in outcomes),
                "object compilation emitted diagnostics")

        executable = build / "apf_link_probe"
        link_command = [
            args.clang, "-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie",
            *map(str, objects), "-o", str(executable),
        ]
        linked = subprocess.run(link_command, capture_output=True, text=True,
                                check=False)
        require(linked.returncode == 0, f"link failed: {linked.stderr[:1000]}")
        require(linked.stdout == "" and linked.stderr == "",
                "link emitted unexpected diagnostics")
        executed = subprocess.run([str(executable)], capture_output=True, text=True,
                                  check=False)
        require(executed.returncode == 0, "non-title mapping harness failed")
        require(executed.stdout == "" and executed.stderr == "",
                "non-title mapping harness emitted output")

        nm = subprocess.run(["nm", "-u", str(executable)], capture_output=True,
                            text=True, check=True).stdout.splitlines()
        unresolved_guest = [line for line in nm
                            if "__imp__" in line or re.search(r"\bsub_[0-9A-F]+", line)]
        require(not unresolved_guest, "linked executable retains guest symbols")
        defined = subprocess.run(["nm", "-C", "--defined-only", str(executable)],
                                 capture_output=True, text=True, check=True).stdout
        defined_import_count = sum(
            f" {name}(PPCContext&, unsigned char*)" in defined
            for name in import_names
        )
        require(defined_import_count == 334, "not all fail-fast imports were linked")
        executable_size = executable.stat().st_size
        object_bytes = sum(path.stat().st_size for path in objects)

    report = {
        "schema": SCHEMA,
        "result": {
            "generated_cpp_object_count": 237,
            "support_object_count": 2,
            "compiled_object_count": 239,
            "compile_failure_count": 0,
            "link_succeeded": True,
            "mapping_only_harness_return_code": 0,
            "undefined_guest_symbol_count": 0,
            "fail_fast_import_definition_count": 334,
            "guest_import_semantics_implemented": False,
            "title_entry_called": False,
            "native_game_boot_proved": False,
        },
        "toolchain": {
            "compiler": args.clang,
            "compiler_version_first_line": version,
            "linker": "ld.lld-18",
            "linker_version": linker_version,
            "compile_flags": ["-std=c++20", "-O0", "-c"],
            "link_flags": ["-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie"],
            "jobs": args.jobs,
        },
        "build_observation": {
            "total_object_bytes": object_bytes,
            "temporary_executable_bytes": executable_size,
            "temporary_outputs_deleted": True,
            "executable_preserved": False,
            "mapping_count_checked_by_harness": 60731,
        },
        "import_boundary": {
            "callable_thunks": len(import_names),
            "imported_data_slots_not_satisfied_by_linking": len(data_items),
            "stub_behavior": "unconditional abort if any guest import is called",
            "stub_source_sha256": digest(stub_text.encode("utf-8")),
            "stub_source_embedded_in_report": False,
        },
        "interpretation": {
            "worked": (
                "All generated APF C++ compiles to objects and links when every "
                "callable guest import has an explicit fail-fast definition."
            ),
            "failed": (
                "The harness does not load the XEX image, initialize imported data, "
                "call title entry, or implement any XAM/xboxkrnl semantics."
            ),
            "conclusion": (
                "Link closure is a mechanical milestone only; the binary is a "
                "symbol-closure probe, not a runnable APF port."
            ),
        },
        "sources": {
            "xex_report": pin(xex_report_path),
            "all_tus_report": pin(all_tus_path),
            "generator": pin(Path(__file__).resolve()),
            "xenonrecomp_commit": commit,
            "generated_cpp_manifest_sha256": EXPECTED_CPP_MANIFEST,
        },
        "portme": [
            "// PORTME: replace all 334 aborting import definitions with exact guest-ABI behavior.",
            "// PORTME: load the decoded guest image and initialize all 13 imported data slots.",
            "// PORTME: resolve switch/function boundaries and 11 missing instruction semantics before calling title entry.",
            "// PORTME: provide scheduler, filesystem, input, audio, Xenos/MMIO and exception behavior before claiming boot.",
        ],
    }
    output = args.json.resolve() if args.json.is_absolute() else (root / args.json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_STATIC_RECOMP_LINK_PROBE_PASS objects=239 link=yes harness=0 "
        "imports=334 guest_undefined=0 title_entry=no runtime=no"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, LinkProbeError,
            subprocess.SubprocessError) as exc:
        raise SystemExit(f"error: {exc}") from exc
