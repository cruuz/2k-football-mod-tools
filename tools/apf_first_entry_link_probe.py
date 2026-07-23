#!/usr/bin/env python3
"""Link APF's generated corpus to the typed first-entry bridge without entry.

The temporary executable maps the exact decoded image, installs all generated
function pointers, calls only the first typed import bridge directly, and then
deletes every object/executable.  It never calls translated APF title code.
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
from typing import Any


EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_DECODED_SIZE = 0x03380000
EXPECTED_CPP_COUNT = 237
EXPECTED_NUMBERED_COUNT = 236
EXPECTED_MAPPING_COUNT = 60731


class LinkProbeError(RuntimeError):
    """Raised when a compile, link, or exact-input invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LinkProbeError(message)


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


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
        "#define APF_NONFRONTIER_IMPORT(symbol) \\\n+    PPC_FUNC(symbol) { (void)ctx; (void)base; fail_closed(); }\n\n".replace(
            "\n+    PPC_FUNC", "\n    PPC_FUNC"),
    ]
    lines.extend(f"APF_NONFRONTIER_IMPORT({name})\n" for name in import_names)
    lines.append("#undef APF_NONFRONTIER_IMPORT\n")
    return "".join(lines)


def harness_source() -> str:
    return r'''#include "ppc_recomp_shared.h"
#include "static_runtime/apf_first_entry_xenon_bridge.h"

#include <cstdint>
#include <cstdio>
#include <fstream>
#include <vector>

static std::vector<std::uint8_t> read_file(const char* path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) return {};
    const std::streamsize size = stream.tellg();
    if (size < 0) return {};
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
    stream.seekg(0);
    if (!stream.read(reinterpret_cast<char*>(bytes.data()), size)) return {};
    return bytes;
}

int main(int argc, char** argv) {
    if (argc != 3) return 2;
    const std::vector<std::uint8_t> image = read_file(argv[1]);
    const std::vector<std::uint8_t> xex = read_file(argv[2]);
    if (image.size() != VC_APF_IMPORTED_DATA_IMAGE_SIZE ||
        xex.size() < VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE) return 3;

    vc_apf_first_entry_config config{};
    config.decoded_image_bytes = image.data();
    config.decoded_image_byte_count = image.size();
    config.raw_xex_prefix_bytes = xex.data();
    config.raw_xex_prefix_byte_count = xex.size();
    config.policy.configured_fields = VC_APF_BOOT_CONFIG_ALL;
    config.policy.process_type = 1;
    config.policy.language = 1;
    config.policy.av_pack = 6;
    config.policy.executable_system_flags = 0x00000200;
    config.policy.vm_arena_base = 0x40000000;
    config.policy.vm_arena_size = 0x10000000;
    config.instruction_budget = 1000000;
    config.function_dispatch_budget = 100000;

    vc_apf_first_entry_state state{};
    if (vc_apf_first_entry_prepare(&state, &config) !=
        VC_APF_FIRST_ENTRY_OK) return 4;
    if (vc_apf_first_entry_xenon_install_dispatch(
            &state, PPCFuncMappings, 60731) != VC_APF_FIRST_ENTRY_OK) return 5;
    if (PPC_LOOKUP_FUNC(state.guest_address_space,
                        VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK) !=
        __imp__RtlImageXexHeaderField) return 6;

    PPCContext context{};
    if (vc_apf_first_entry_xenon_context_init(&context) !=
        VC_APF_FIRST_ENTRY_OK) return 7;
    context.lr = VC_APF_FIRST_ENTRY_FIRST_IMPORT_RETURN;
    context.r3.u64 = state.imported_data.raw_xex_prefix;
    context.r4.u64 = VC_APF_IMPORTED_DATA_XEX_DEFAULT_HEAP_SIZE;
    if (vc_apf_first_entry_xenon_bridge_bind(&state) !=
        VC_APF_FIRST_ENTRY_OK) return 8;
    bool stopped = false;
    try {
        __imp__RtlImageXexHeaderField(context, state.guest_address_space);
    } catch (const vc_apf_first_entry_boundary_stop& stop) {
        stopped = stop.gate_status == VC_APF_FIRST_ENTRY_OK &&
                  stop.adapter_status == VC_APF_BOOT_LEAF_OK &&
                  stop.import_thunk == VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK;
    }
    vc_apf_first_entry_xenon_bridge_unbind();
    if (!stopped || context.r3.u64 != 0) return 9;
    if (vc_apf_first_entry_probe_expected_boundary(&state) !=
        VC_APF_FIRST_ENTRY_OK) return 10;

    vc_apf_first_entry_readiness_result readiness{};
    vc_apf_first_entry_readiness(&state, &readiness);
    if (readiness.blocker_count != 2 || readiness.entry_call_authorized ||
        readiness.entry_called) return 11;
    std::printf("APF_FIRST_ENTRY_LINK_PASS mappings=%zu typed_bindings=%u "
                "first_thunk=0x%08X bridge_stop=1 blockers=%zu "
                "entry_authorized=0 entry_called=0\n",
                state.generated_dispatch_mapping_count,
                VC_APF_FIRST_ENTRY_FRONTIER_IMPORT_COUNT,
                VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK,
                readiness.blocker_count);
    vc_apf_first_entry_destroy(&state);
    return 0;
}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--generated", type=Path,
                        default=Path("build-static-recomp-apf/ppc-filtered"))
    parser.add_argument("--xex-report", type=Path, default=Path(
        "reports/headers/apf2k8_xex_report.json"))
    parser.add_argument("--xex", type=Path, default=Path(
        "extracted/All-Pro Football 2K8 (USA)/default.xex"))
    parser.add_argument("--decoded", type=Path, required=True)
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
    xex_report_path = resolve(args.xex_report)
    xex = resolve(args.xex)
    decoded = resolve(args.decoded)
    temp_root = resolve(args.temp_root)
    transcript = resolve(args.transcript)
    clang = shutil.which(args.clang)
    clangxx = shutil.which(args.clangxx)
    require(args.jobs > 0 and clang is not None and clangxx is not None,
            "pinned compiler or positive job count is unavailable")
    require(generated.is_dir() and xex_report_path.is_file() and
            xex.is_file() and decoded.is_file(), "link-probe input is missing")
    require(sha256_file(xex) == EXPECTED_XEX_SHA256,
            "retail XEX hash changed")
    require(decoded.stat().st_size == EXPECTED_DECODED_SIZE and
            sha256_file(decoded) == EXPECTED_DECODED_SHA256,
            "decoded image is not exact")

    sources = [generated / "ppc_func_mapping.cpp", *[
        generated / f"ppc_recomp.{index}.cpp"
        for index in range(EXPECTED_NUMBERED_COUNT)
    ]]
    require(len(sources) == EXPECTED_CPP_COUNT and
            all(path.is_file() for path in sources),
            "generated source roster changed")
    xex_data = json.loads(xex_report_path.read_text(encoding="utf-8"))
    all_imports = ["__imp__" + item["name"]
                   for item in xex_data["imports"]["items"]
                   if item["thunk_address"] is not None]
    bridge_text = (root / "src/static_runtime/apf_first_entry_xenon_bridge.cpp").read_text(
        encoding="utf-8")
    typed = set(re.findall(
        r"^VC_APF_DEFINE_IMPORT\((__imp__[A-Za-z0-9_]+),",
        bridge_text, re.MULTILINE))
    require(len(all_imports) == 334 and len(typed) == 30 and
            typed < set(all_imports), "typed/nonfrontier import split changed")
    nonfrontier = sorted(set(all_imports) - typed)
    require(len(nonfrontier) == 304, "nonfrontier import count changed")

    include_paths = [
        root / "include", generated,
        root / "tools/vendor/XenonRecomp/XenonUtils",
        root / "tools/vendor/XenonRecomp/thirdparty/simde",
    ]
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apf-first-entry-link-",
                                     dir=temp_root) as temporary:
        build = Path(temporary)
        stubs = build / "nonfrontier_imports.cpp"
        harness = build / "harness.cpp"
        stubs.write_text(stub_source(nonfrontier), encoding="utf-8")
        harness.write_text(harness_source(), encoding="utf-8")
        cpp_sources = [
            *sources,
            root / "src/static_runtime/apf_first_entry_xenon_bridge.cpp",
            stubs, harness,
        ]
        c_sources = [
            root / "src/static_runtime/apf_first_entry_gate.c",
            root / "src/static_runtime/apf_imported_data_bootstrap.c",
            root / "src/static_runtime/apf_boot_leaf_adapters.c",
        ]
        compile_specs: list[tuple[list[str], Path]] = []
        for index, source in enumerate(cpp_sources):
            output = build / f"cpp-{index:03d}.o"
            command = [clangxx, "-std=c++20", "-O0", "-c", str(source),
                       "-o", str(output)]
            command.extend(f"-I{path}" for path in include_paths)
            compile_specs.append((command, output))
        for index, source in enumerate(c_sources):
            output = build / f"c-{index:03d}.o"
            command = [clang, "-std=c11", "-O0", "-D_GNU_SOURCE", "-c",
                       str(source), "-o", str(output),
                       f"-I{root / 'include'}"]
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
                "object compilation failed: " +
                " | ".join(item["stderr"][-600:] for item in failures[:3]))
        require(all(item["output"].is_file() for item in outcomes),
                "compiled object is missing")

        executable = build / "apf_first_entry_link_probe"
        objects = [output for _, output in compile_specs]
        linked = subprocess.run([
            clangxx, "-fuse-ld=lld", "-Wl,--build-id=none", "-no-pie",
            *map(str, objects), "-o", str(executable),
        ], capture_output=True, text=True, check=False)
        require(linked.returncode == 0, "link failed: " + linked.stderr[-1500:])
        executed = subprocess.run(
            [str(executable), str(decoded), str(xex)],
            capture_output=True, text=True, check=False, timeout=60)
        require(executed.returncode == 0,
                f"non-title linked harness failed ({executed.returncode}): "
                + executed.stderr[-1000:])
        lines = [line for line in executed.stdout.splitlines()
                 if line.startswith("APF_FIRST_ENTRY_LINK_PASS ")]
        require(len(lines) == 1 and executed.stderr == "",
                "linked harness transcript changed")
        line = lines[0]
        require("mappings=60731" in line and "typed_bindings=30" in line and
                "entry_authorized=0" in line and "entry_called=0" in line,
                "linked harness invariant changed")
        object_bytes = sum(path.stat().st_size for path in objects)

    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(line + "\n", encoding="utf-8")
    print(line)
    print(
        "APF_FIRST_ENTRY_LINK_BUILD_PASS "
        f"generated_cpp={EXPECTED_CPP_COUNT} typed_imports={len(typed)} "
        f"nonfrontier_failfast={len(nonfrontier)} object_bytes={object_bytes} "
        "temporary_outputs_deleted=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
