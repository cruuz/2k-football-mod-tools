#!/usr/bin/env python3
"""Resolve the bounded indirect calls in APF's pre-title entry frontier.

This extends apf_static_boot_import_frontier.py.  It decodes the untouched XEX
to a temporary file, independently reads the same words through Ghidra, checks
the generated address mapping, and admits only targets proved for the _xstart
entry context.  It never invokes translated title code.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
from typing import Any


SCHEMA = "apf2k8_boot_indirect_frontier/v1"
EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_DECODED_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_DECODED_SIZE = 0x03380000
EXPECTED_IMAGE_BASE = 0x82000000
EXPECTED_XENONUTILS_SHA256 = (
    "0653cc0005ae3904e0c8e856678101dcf54d887a1f1f96702e7f5e5205692b37"
)
EXPECTED_VENDOR_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
EXPECTED_ORIGINAL_SITE_COUNT = 15
EXPECTED_RESOLVED_SITE_COUNT = 10
EXPECTED_UNRESOLVED_SITE_COUNT = 5
EXPECTED_PROVED_TARGET_REFERENCE_COUNT = 254
EXPECTED_UNIQUE_PROVED_TARGET_COUNT = 253

MAPPING = re.compile(
    r"\{\s*0x([0-9A-Fa-f]+),\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}"
)
INDIRECT_WITH_LR = re.compile(
    r"ctx\.lr = 0x([0-9A-Fa-f]+);\s*\n\s*"
    r"PPC_CALL_INDIRECT_FUNC\(ctx\.ctr\.u32\);"
)


class IndirectFrontierError(RuntimeError):
    """Raised when an input pin or proof invariant has changed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise IndirectFrontierError(message)


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def fmt(value: int) -> str:
    return f"0x{value:08X}"


def load_frontier_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(
        "apf_static_boot_import_frontier", path
    )
    require(spec is not None and spec.loader is not None,
            "cannot load direct-frontier module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_checked(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command, capture_output=True, text=True, check=False, **kwargs
    )
    require(
        completed.returncode == 0,
        f"command failed ({command[0]}): {completed.stderr[-1500:]}",
    )
    return completed


def decode_xex(
    root: Path,
    xex: Path,
    extractor_source: Path,
    vendor: Path,
    compiler: str,
    directory: Path,
) -> bytes:
    library = vendor / "build/XenonUtils/libXenonUtils.a"
    require(library.is_file(), "pinned XenonUtils library is missing")
    require(sha256_file(library) == EXPECTED_XENONUTILS_SHA256,
            "pinned XenonUtils library changed")
    executable = directory / "xex_extract_pe"
    decoded = directory / "apf-decoded.pe"
    compile_command = [
        compiler, "-std=c++20", "-O2", str(extractor_source),
        f"-I{vendor / 'XenonUtils'}",
        f"-I{vendor / 'thirdparty/TinySHA1'}",
        f"-I{vendor / 'thirdparty/tiny-AES-c'}",
        str(library), "-o", str(executable),
    ]
    compiled = run_checked(compile_command)
    require(compiled.stdout == "" and compiled.stderr == "",
            "XEX extractor compilation emitted diagnostics")
    extracted = run_checked([str(executable), str(xex), str(decoded)])
    require(
        extracted.stdout == (
            "blocks=642 chunks=1648 lzx_bytes=37717546 "
            "image_bytes=54001664 window_size=32768\n"
        ) and extracted.stderr == "",
        "XEX extraction transcript changed",
    )
    require(decoded.stat().st_size == EXPECTED_DECODED_SIZE,
            "decoded image size changed")
    require(sha256_file(decoded) == EXPECTED_DECODED_SHA256,
            "decoded image hash changed")
    return decoded.read_bytes()


def run_ghidra(
    root: Path,
    ghidra: Path,
    project_directory: Path,
    script_directory: Path,
    script: Path,
    output: Path,
) -> list[dict[str, str]]:
    require(ghidra.is_file() and os.access(ghidra, os.X_OK),
            "Ghidra analyzeHeadless is unavailable")
    require((project_directory / "apf2k8.gpr").is_file(),
            "APF Ghidra project is unavailable")
    environment = os.environ.copy()
    environment.update({
        "HOME": str(root / "tools/ghidra-home"),
        "XDG_CONFIG_HOME": str(root / "tools/ghidra-home/.config"),
        "JAVA_HOME": "/usr/lib/jvm/java-21-openjdk-amd64",
    })
    run_checked([
        str(ghidra), str(project_directory), "apf2k8",
        "-process", "default.xex", "-readOnly", "-noanalysis",
        "-scriptPath", str(script_directory),
        "-postScript", script.name, str(output),
    ], env=environment)
    require(output.is_file(), "Ghidra evidence was not produced")
    with output.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    require(rows and set(rows[0]) == {
        "record", "address", "value_or_bytes", "detail"
    }, "Ghidra evidence schema changed")
    return rows


def read_be32(image: bytes, address: int) -> int:
    offset = address - EXPECTED_IMAGE_BASE
    require(0 <= offset <= len(image) - 4,
            f"decoded read outside image: {fmt(address)}")
    return struct.unpack_from(">I", image, offset)[0]


def range_values(image: bytes, first: int, after_last: int) -> list[tuple[int, int]]:
    require(first % 4 == 0 and after_last % 4 == 0 and first < after_last,
            "invalid word range")
    return [(address, read_be32(image, address))
            for address in range(first, after_last, 4)]


def site_specs() -> dict[int, dict[str, Any]]:
    """Proof rules for exactly the original 15 entry-shell sites."""
    unresolved = "unresolved_dynamic"
    resolved = "proved_bounded"
    return {
        0x84BDAFA0: {
            "caller": "sub_84BDAF80", "status": unresolved,
            "source": "r11 <- BE32[0x852D6464]",
            "provenance": (
                "zero-initialized writable callback slot; sub_84BDAF70 stores "
                "an unconstrained r3 and the call is guarded only by value != 0"
            ),
            "portme": (
                "PORTME at 0x84BDAFA0: recover every runtime registration into "
                "0x852D6464 and bound the callback before admitting an edge."
            ),
        },
        0x84BDDF90: {
            "caller": "sub_84BDDF70", "status": unresolved,
            "source": "r11 <- BE32[0x852D5C24]",
            "provenance": (
                "zero-initialized writable callback slot; sub_84BDDEF8 and the "
                "locked exchange sub_84BDDF08 accept unconstrained r3 values"
            ),
            "portme": (
                "PORTME at 0x84BDDF90: recover registrations into 0x852D5C24 "
                "and prove the allocation-retry callback target set."
            ),
        },
        0x84BDE678: {
            "caller": "sub_84BDE638", "status": resolved,
            "source": "r11 <- BE32[0x852D5DBC]",
            "provenance": (
                "on every _xstart path reaching this site, sub_84BDACA0 first "
                "stores zero through sub_84BDE5F8; the local zero case then "
                "stores and retains constant 0x84BDE608 before mtctr"
            ),
            "target_addresses": [0x84BDE608],
        },
        0x84BDE7E4: {
            "caller": "sub_84BDE7B0", "status": resolved,
            "source": "r11 <- BE32[0x852D5DD8]",
            "provenance": (
                "dominating store at 0x84BDEAE0 writes constant 0x84D0837C; "
                "the only entry-frontier call is the later failure cleanup"
            ),
            "target_addresses": [0x84D0837C],
        },
        0x84BDE878: {
            "caller": "sub_84BDE840", "status": resolved,
            "source": "r11 <- KeTlsGetValue(BE32[0x84F01AA4])",
            "provenance": (
                "the successful initialization path stores 0x84D0835C in "
                "0x852D5DD0 and passes that exact value to KeTlsSetValue; all "
                "entry-frontier calls reaching this site occur after that guard"
            ),
            "target_addresses": [0x84D0835C],
        },
        0x84BDE8AC: {
            "caller": "sub_84BDE840", "status": resolved,
            "source": "r11 <- BE32[0x852D5DD4]",
            "provenance": (
                "dominating entry initializer at 0x84BDEAD8 writes constant "
                "0x84D0836C"
            ),
            "target_addresses": [0x84D0836C],
        },
        0x84BDEB28: {
            "caller": "sub_84BDEA98", "status": resolved,
            "source": "r11 <- BE32[0x852D5DCC]",
            "provenance": (
                "same-function dominating store at 0x84BDEAC0 writes constant "
                "0x84BDE6F8"
            ),
            "target_addresses": [0x84BDE6F8],
        },
        0x84BDEB60: {
            "caller": "sub_84BDEA98", "status": resolved,
            "source": "r11 <- BE32[0x852D5DD4]",
            "provenance": (
                "same-function dominating store at 0x84BDEAD8 writes constant "
                "0x84D0836C"
            ),
            "target_addresses": [0x84D0836C],
        },
        0x84BEBDEC: {
            "caller": "sub_84BEBD58", "status": unresolved,
            "source": "r11 <- BE32[r3 + 0x584]",
            "provenance": (
                "allocator-object callback field selected at runtime; a null "
                "field falls back to NtAllocateVirtualMemory, but no bounded "
                "non-null writer is present in the 74-function frontier"
            ),
            "portme": (
                "PORTME at 0x84BEBDEC: recover construction and all writes to "
                "allocator field +0x584 before dispatching its non-null value."
            ),
        },
        0x84BF0C94: {
            "caller": "sub_84BF0C50", "status": unresolved,
            "source": "r11 <- BE32[current intrusive-list node + 8]",
            "provenance": (
                "the decoded 0x84F02440 sentinel is initially self-linked, but "
                "sub_84BF0CD0 can register writable nodes with callback +8"
            ),
            "portme": (
                "PORTME at 0x84BF0C94: enumerate all registrations into the "
                "0x84F02440 intrusive callback list and preserve their order."
            ),
        },
        0x84BF1724: {
            "caller": "sub_84BF16F8", "status": resolved,
            "source": "r10 <- BE32[0x844D1B0C]; r11 <- rotlwi(r10, 0)",
            "provenance": (
                "single read-only .rdata word independently matched by decoded "
                "XEX and Ghidra"
            ),
            "target_ranges": [(0x844D1B0C, 0x844D1B10)],
        },
        0x84BF1760: {
            "caller": "sub_84BF16F8", "status": resolved,
            "source": "r11 <- BE32[r31], r31 scans [0x84D103E4,0x84D103F0)",
            "provenance": (
                "fixed three-word CRT initializer range; null entries are "
                "skipped and every non-null word has an exact generated mapping"
            ),
            "target_ranges": [(0x84D103E4, 0x84D103F0)],
        },
        0x84BF17AC: {
            "caller": "sub_84BF16F8", "status": resolved,
            "source": "r11 <- BE32[r31], r31 scans [0x84D10010,0x84D103E0)",
            "provenance": (
                "fixed 244-word CRT constructor range; null entries are skipped "
                "and all 243 non-null words have exact generated mappings"
            ),
            "target_ranges": [(0x84D10010, 0x84D103E0)],
        },
        0x84BF1824: {
            "caller": "sub_84BF17D8", "status": resolved,
            "source": "r11 <- BE32[r31], r31 scans [0x84D10000,0x84D1000C)",
            "provenance": (
                "fixed three-word CRT error-initializer range; null entries are "
                "skipped and both non-null words have exact generated mappings"
            ),
            "target_ranges": [(0x84D10000, 0x84D1000C)],
        },
        0x84BF198C: {
            "caller": "sub_84BF1950", "status": unresolved,
            "source": "r11 <- BE32[BE32[KeDebugMonitorData slot 0x82000940] + 24]",
            "provenance": (
                "kernel-owned imported data and a runtime object callback field; "
                "the retail ordinal word is not a runtime pointer"
            ),
            "portme": (
                "PORTME at 0x84BF198C: seed KeDebugMonitorData with an ABI-correct "
                "guest object and identify its +24 callback contract."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--xex", type=Path, default=Path(
        "extracted/All-Pro Football 2K8 (USA)/default.xex"))
    parser.add_argument("--generated", type=Path,
                        default=Path("build-static-recomp-apf/ppc-filtered"))
    parser.add_argument("--frontier-tool", type=Path,
                        default=Path("tools/apf_static_boot_import_frontier.py"))
    parser.add_argument("--frontier-report", type=Path, default=Path(
        "reports/static_recomp/apf2k8_static_boot_import_frontier.json"))
    parser.add_argument("--xex-report", type=Path,
                        default=Path("reports/headers/apf2k8_xex_report.json"))
    parser.add_argument("--extractor-source", type=Path,
                        default=Path("tools/xex_extract_pe.cpp"))
    parser.add_argument("--vendor", type=Path,
                        default=Path("tools/vendor/XenonRecomp"))
    parser.add_argument("--ghidra", type=Path, default=Path(
        "tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless"))
    parser.add_argument("--ghidra-projects", type=Path,
                        default=Path("ghidra_projects"))
    parser.add_argument("--ghidra-script", type=Path, default=Path(
        "tools/ghidra_scripts/apf/ApfBootIndirectFrontier.java"))
    parser.add_argument("--clang", default="clang++-18")
    parser.add_argument("--temp-root", type=Path, default=Path(".codex-tmp"))
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    resolve = lambda value: value.resolve() if value.is_absolute() \
        else (root / value).resolve()
    xex = resolve(args.xex)
    generated = resolve(args.generated)
    frontier_tool_path = resolve(args.frontier_tool)
    frontier_report_path = resolve(args.frontier_report)
    xex_report_path = resolve(args.xex_report)
    extractor_source = resolve(args.extractor_source)
    vendor = resolve(args.vendor)
    ghidra = resolve(args.ghidra)
    ghidra_projects = resolve(args.ghidra_projects)
    ghidra_script = resolve(args.ghidra_script)
    temp_root = resolve(args.temp_root)
    output_json = resolve(args.json)
    output_tsv = resolve(args.tsv)
    for path in (xex, frontier_tool_path, frontier_report_path,
                 xex_report_path, extractor_source, ghidra_script):
        require(path.is_file(), f"required input is missing: {path}")
    require(generated.is_dir() and vendor.is_dir(), "generated/vendor input missing")
    require(sha256_file(xex) == EXPECTED_XEX_SHA256,
            "untouched retail XEX hash changed")
    compiler = shutil.which(args.clang)
    require(compiler is not None, f"compiler unavailable: {args.clang}")

    frontier_module = load_frontier_module(frontier_tool_path)
    numbered = [generated / f"ppc_recomp.{index}.cpp"
                for index in range(frontier_module.EXPECTED_NUMBERED_SOURCE_COUNT)]
    require(all(path.is_file() for path in numbered),
            "numbered generated source is missing")
    calls, indirect_counts, origins, bodies = frontier_module.parse_generated(numbered)
    mapping_path = generated / "ppc_func_mapping.cpp"
    require(sha256_file(mapping_path) == frontier_module.EXPECTED_MAPPING_SHA256,
            "generated function mapping changed")
    mapping_rows = MAPPING.findall(mapping_path.read_text(encoding="utf-8"))
    address_to_symbol = {int(address, 16): symbol
                         for address, symbol in mapping_rows}
    symbol_to_address = {symbol: address for address, symbol in address_to_symbol.items()}
    require(len(address_to_symbol) == frontier_module.EXPECTED_MAPPING_COUNT,
            "mapping count changed")
    generated_manifest_rows = [{
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    } for path in [mapping_path, *numbered]]
    generated_manifest_sha256 = frontier_module.manifest_digest(
        generated_manifest_rows)
    require(generated_manifest_sha256 ==
            frontier_module.EXPECTED_CPP_MANIFEST_SHA256,
            "generated C++ manifest changed")
    vendor_commit = run_checked(
        ["git", "-C", str(vendor), "rev-parse", "HEAD"]
    ).stdout.strip()
    require(vendor_commit == EXPECTED_VENDOR_COMMIT,
            "pinned XenonRecomp commit changed")
    vendor_diff = subprocess.run(
        ["git", "-C", str(vendor), "diff", "--quiet"], check=False
    )
    require(vendor_diff.returncode == 0,
            "tracked XenonRecomp baseline has local changes")

    xex_report = json.loads(xex_report_path.read_text(encoding="utf-8"))
    callable_items = [item for item in xex_report["imports"]["items"]
                      if item["thunk_address"] is not None]
    callable_by_symbol = {"__imp__" + item["name"]: item
                          for item in callable_items}
    callable_imports = set(callable_by_symbol)
    original_generated, original_imports = frontier_module.closure(
        calls, callable_imports, frontier_module.BOUNDARIES
    )
    original_active = original_generated - frontier_module.BOUNDARIES
    require((len(original_generated), len(original_imports)) == (76, 27),
            "original boundary-stopped frontier changed")
    require(sum(indirect_counts[name] for name in original_active) == 15,
            "original indirect site count changed")
    frontier_report = json.loads(frontier_report_path.read_text(encoding="utf-8"))
    require(frontier_report["schema"] == frontier_module.SCHEMA,
            "direct-frontier report schema changed")
    require(frontier_report["result"]["boundary_stopped_total_nodes"] == 103,
            "direct-frontier report count changed")

    discovered: dict[int, dict[str, str]] = {}
    for caller in sorted(original_active):
        for match in INDIRECT_WITH_LR.finditer(bodies[caller]):
            return_address = int(match.group(1), 16)
            call_address = return_address - 4
            require(call_address not in discovered,
                    f"duplicate indirect site {fmt(call_address)}")
            discovered[call_address] = {
                "caller": caller,
                "return_address": fmt(return_address),
                "generated_source": origins[caller][0],
                "generated_internal_symbol": origins[caller][1],
            }
    specs = site_specs()
    require(len(specs) == EXPECTED_ORIGINAL_SITE_COUNT,
            "proof rule count changed")
    require(set(discovered) == set(specs),
            "generated original indirect-site addresses changed")
    require(all(discovered[address]["caller"] == spec["caller"]
                for address, spec in specs.items()),
            "generated indirect caller changed")

    input_hashes_before = {
        "xex": sha256_file(xex),
        "mapping": sha256_file(mapping_path),
        "frontier_tool": sha256_file(frontier_tool_path),
        "frontier_report": sha256_file(frontier_report_path),
        "ghidra_script": sha256_file(ghidra_script),
        "generated_manifest": generated_manifest_sha256,
    }
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="apf-indirect-frontier-",
                                     dir=temp_root) as temporary:
        directory = Path(temporary)
        image = decode_xex(root, xex, extractor_source, vendor,
                           compiler, directory)
        ghidra_output = directory / "ghidra.tsv"
        ghidra_rows = run_ghidra(
            root, ghidra, ghidra_projects, ghidra_script.parent,
            ghidra_script, ghidra_output,
        )

        ghidra_calls = {
            int(row["address"], 0): row for row in ghidra_rows
            if row["record"] == "call"
        }
        ghidra_words = {
            int(row["address"], 0): int(row["value_or_bytes"], 0)
            for row in ghidra_rows if row["record"] == "word"
        }
        ghidra_xrefs = {
            int(row["address"], 0): row for row in ghidra_rows
            if row["record"] == "xrefs"
        }
        require(set(specs) <= set(ghidra_calls),
                "Ghidra omitted an original indirect site")
        for address in specs:
            row = ghidra_calls[address]
            raw = image[address - EXPECTED_IMAGE_BASE:
                        address - EXPECTED_IMAGE_BASE + 4]
            require(raw.hex().upper() == "4E800421",
                    f"decoded call opcode changed at {fmt(address)}")
            require(row["value_or_bytes"] == "4E 80 04 21" and
                    row["detail"].startswith("bctrl;"),
                    f"Ghidra call decode changed at {fmt(address)}")

        word_ranges = [
            (0x844D1B0C, 0x844D1B10),
            (0x84D10000, 0x84D1000C),
            (0x84D10010, 0x84D103E0),
            (0x84D103E4, 0x84D103F0),
            (0x852D5C24, 0x852D5C28),
            (0x852D5DBC, 0x852D5DDC),
            (0x852D6464, 0x852D6468),
        ]
        checked_words = []
        for first, after_last in word_ranges:
            for address, value in range_values(image, first, after_last):
                require(ghidra_words.get(address) == value,
                        f"decoded/Ghidra word mismatch at {fmt(address)}")
                checked_words.append(address)

        site_rows: list[dict[str, Any]] = []
        proved_edges_by_caller: dict[str, set[str]] = defaultdict(set)
        all_proved_targets: set[str] = set()
        table_summaries: list[dict[str, Any]] = []
        for address in sorted(specs):
            spec = specs[address]
            target_addresses = list(spec.get("target_addresses", []))
            range_summaries = []
            for first, after_last in spec.get("target_ranges", []):
                values = range_values(image, first, after_last)
                non_null = [(slot, value) for slot, value in values
                            if value not in {0, 0xFFFFFFFF}]
                target_addresses.extend(value for _, value in non_null)
                range_summary = {
                    "first": fmt(first),
                    "after_last": fmt(after_last),
                    "entry_count": len(values),
                    "null_entry_count": sum(value == 0 for _, value in values),
                    "minus_one_entry_count": sum(
                        value == 0xFFFFFFFF for _, value in values),
                    "non_null_target_count": len(non_null),
                    "raw_sha256": hashlib.sha256(b"".join(
                        struct.pack(">I", value) for _, value in values
                    )).hexdigest(),
                }
                range_summaries.append(range_summary)
                table_summaries.append({
                    "site": fmt(address), **range_summary,
                })
            require(len(target_addresses) == len(set(target_addresses)),
                    f"duplicate target in site {fmt(address)}")
            target_items = []
            for target_address in target_addresses:
                require(target_address in address_to_symbol,
                        f"target has no exact generated mapping: {fmt(target_address)}")
                symbol = address_to_symbol[target_address]
                if symbol in calls:
                    classification = "generated_implementation"
                elif symbol in callable_imports:
                    classification = "callable_import"
                else:
                    raise IndirectFrontierError(
                        f"mapped target is unclassified: {symbol}")
                target_items.append({
                    "address": fmt(target_address),
                    "symbol": symbol,
                    "classification": classification,
                })
                proved_edges_by_caller[spec["caller"]].add(symbol)
                all_proved_targets.add(symbol)
            if spec["status"] == "proved_bounded":
                require(target_items,
                        f"resolved site has no targets: {fmt(address)}")
            else:
                require(not target_items and "portme" in spec,
                        f"unresolved site is not fail-closed: {fmt(address)}")
            site_rows.append({
                "call_instruction_address": fmt(address),
                "return_address": discovered[address]["return_address"],
                "caller": spec["caller"],
                "generated_source": discovered[address]["generated_source"],
                "generated_internal_symbol":
                    discovered[address]["generated_internal_symbol"],
                "ctr_source": spec["source"],
                "value_provenance": spec["provenance"],
                "classification": spec["status"],
                "proved_target_count": len(target_items),
                "proved_targets": target_items,
                "table_ranges": range_summaries,
                "ghidra_instruction_bytes":
                    ghidra_calls[address]["value_or_bytes"],
                "ghidra_instruction":
                    ghidra_calls[address]["detail"].split(";", 1)[0],
                "portme": spec.get("portme"),
            })

    resolved_sites = [row for row in site_rows
                      if row["classification"] == "proved_bounded"]
    unresolved_sites = [row for row in site_rows
                        if row["classification"] == "unresolved_dynamic"]
    require(len(resolved_sites) == EXPECTED_RESOLVED_SITE_COUNT and
            len(unresolved_sites) == EXPECTED_UNRESOLVED_SITE_COUNT,
            "resolved/unresolved site counts changed")
    proved_target_references = sum(
        row["proved_target_count"] for row in resolved_sites
    )
    require(proved_target_references == EXPECTED_PROVED_TARGET_REFERENCE_COUNT,
            "proved target reference count changed")
    require(len(all_proved_targets) == EXPECTED_UNIQUE_PROVED_TARGET_COUNT,
            "unique proved target count changed")
    require(sum(symbol in calls for symbol in all_proved_targets) == 250 and
            sum(symbol in callable_imports for symbol in all_proved_targets) == 3,
            "proved target classification counts changed")

    reached_generated: set[str] = set()
    reached_imports: set[str] = set()
    pending: deque[str] = deque([frontier_module.ENTRY])
    while pending:
        caller = pending.popleft()
        if caller in reached_generated:
            continue
        require(caller in calls, f"augmented closure lacks body: {caller}")
        reached_generated.add(caller)
        if caller in frontier_module.BOUNDARIES:
            continue
        for callee in sorted(set(calls[caller]) |
                             proved_edges_by_caller.get(caller, set())):
            if callee in calls:
                if callee not in reached_generated:
                    pending.append(callee)
            elif callee in callable_imports:
                reached_imports.add(callee)
            else:
                raise IndirectFrontierError(
                    f"augmented closure has unknown callee: {callee}")
    active = reached_generated - frontier_module.BOUNDARIES
    direct_sites = [(caller, callee) for caller in active
                    for callee in calls[caller]]
    direct_edges = set(direct_sites)
    generated_edges = {(caller, callee) for caller, callee in direct_edges
                       if callee in calls}
    import_edges = direct_edges - generated_edges
    proved_edge_pairs = {(caller, callee)
                         for caller, targets in proved_edges_by_caller.items()
                         for callee in targets}
    require(len(proved_edge_pairs) == EXPECTED_PROVED_TARGET_REFERENCE_COUNT,
            "proved caller/target edge count changed")
    require((len(reached_generated), len(reached_imports)) == (428, 30),
            "augmented frontier node counts changed")
    require(len(active) == 426, "augmented descended-node count changed")
    require((len(direct_sites), len(direct_edges), len(generated_edges),
             len(import_edges)) == (1484, 796, 721, 75),
            "augmented direct-edge measurements changed")
    require(sum(callee in callable_imports for _, callee in direct_sites) == 87,
            "augmented direct import-site count changed")
    new_imports = reached_imports - original_imports
    require(new_imports == {
        "__imp__ExCreateThread", "__imp__KeBugCheck",
        "__imp__RtlInitAnsiString",
    }, "new augmented import set changed")
    require(len(reached_generated - original_generated) == 352,
            "new augmented generated-node count changed")
    require(sum(indirect_counts[name] for name in active) == 17 and
            sum(indirect_counts[name] > 0 for name in active) == 13,
            "augmented residual indirect-site counts changed")

    newly_exposed = []
    for caller in sorted(active - original_active):
        if indirect_counts[caller] == 0:
            continue
        matches = list(INDIRECT_WITH_LR.finditer(bodies[caller]))
        require(len(matches) == indirect_counts[caller],
                f"new indirect syntax is not bctrl-with-LR in {caller}")
        for match in matches:
            call_address = int(match.group(1), 16) - 4
            if call_address == 0x8468CF4C:
                source = "r28 <- incoming r6"
                reason = (
                    "second-wave argument propagation from sub_84A13580 was "
                    "not admitted by this original-15 bounded pass"
                )
            elif call_address == 0x84BDAA00:
                source = "r11 <- BE32[0x84F01540]"
                reason = (
                    "second-wave cleanup callback state became reachable only "
                    "after descending the admitted constructor targets"
                )
            else:
                raise IndirectFrontierError(
                    f"unexpected newly exposed site: {fmt(call_address)}")
            newly_exposed.append({
                "call_instruction_address": fmt(call_address),
                "return_address": fmt(call_address + 4),
                "caller": caller,
                "generated_source": origins[caller][0],
                "ctr_source": source,
                "classification": "newly_exposed_not_admitted",
                "reason": reason,
                "portme": (
                    f"PORTME at {fmt(call_address)}: complete a second-wave "
                    "context-sensitive target proof before adding this edge."
                ),
            })
    require(len(newly_exposed) == 2, "newly exposed indirect-site count changed")

    xref_addresses = [
        0x82000940, 0x84F02440, 0x852D5C24, 0x852D5DBC,
        0x852D5DCC, 0x852D5DD0, 0x852D5DD4, 0x852D5DD8,
        0x852D6464,
    ]
    xref_evidence = []
    for address in xref_addresses:
        row = ghidra_xrefs[address]
        xref_evidence.append({
            "address": fmt(address),
            "reference_count": int(row["value_or_bytes"]),
            "references": row["detail"].split(";") if row["detail"] else [],
        })

    input_hashes_after = {
        "xex": sha256_file(xex),
        "mapping": sha256_file(mapping_path),
        "frontier_tool": sha256_file(frontier_tool_path),
        "frontier_report": sha256_file(frontier_report_path),
        "ghidra_script": sha256_file(ghidra_script),
        "generated_manifest": frontier_module.manifest_digest([{
            "name": path.name,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        } for path in [mapping_path, *numbered]]),
    }
    require(input_hashes_before == input_hashes_after,
            "an immutable analysis input changed during the run")

    imports_by_library = Counter(
        callable_by_symbol[symbol]["library"] for symbol in reached_imports
    )
    report = {
        "schema": SCHEMA,
        "result": {
            "original_boundary_stopped_descended_functions": 74,
            "original_indirect_sites_classified": len(site_rows),
            "original_indirect_sites_proved_bounded": len(resolved_sites),
            "original_indirect_sites_unresolved": len(unresolved_sites),
            "proved_target_references": proved_target_references,
            "unique_proved_targets": len(all_proved_targets),
            "unique_proved_generated_targets": 250,
            "unique_proved_import_targets": 3,
            "augmented_total_nodes": len(reached_generated) + len(reached_imports),
            "augmented_generated_nodes_including_boundaries":
                len(reached_generated),
            "augmented_callable_imports": len(reached_imports),
            "newly_exposed_indirect_sites": len(newly_exposed),
            "all_indirect_targets_resolved": False,
            "successful_boot_path_proved": False,
            "translated_title_code_executed": False,
            "retail_or_decoded_bytes_embedded": False,
            "temporary_decoded_bytes_deleted": True,
            "immutable_inputs_unchanged": True,
        },
        "inputs": {
            "retail_xex": {
                "path": relative(xex, root),
                "size": xex.stat().st_size,
                "sha256": input_hashes_after["xex"],
            },
            "decoded_image": {
                "temporary_only": True,
                "size": EXPECTED_DECODED_SIZE,
                "sha256": EXPECTED_DECODED_SHA256,
                "preserved_after_run": False,
            },
            "generated_directory": relative(generated, root),
            "generated_cpp_manifest_sha256":
                input_hashes_after["generated_manifest"],
            "generated_mapping": {
                "path": relative(mapping_path, root),
                "sha256": input_hashes_after["mapping"],
                "mapping_count": len(address_to_symbol),
            },
            "direct_frontier_tool": {
                "path": relative(frontier_tool_path, root),
                "sha256": input_hashes_after["frontier_tool"],
            },
            "direct_frontier_report": {
                "path": relative(frontier_report_path, root),
                "sha256": input_hashes_after["frontier_report"],
                "schema": frontier_report["schema"],
            },
            "ghidra_script": {
                "path": relative(ghidra_script, root),
                "sha256": input_hashes_after["ghidra_script"],
                "project": "ghidra_projects/apf2k8.gpr:/default.xex",
                "project_opened_read_only": True,
                "analysis_rerun": False,
            },
            "xenonrecomp_vendor": {
                "path": relative(vendor, root),
                "commit": vendor_commit,
                "tracked_diff_empty": True,
                "untracked_build_directory_ignored": True,
            },
        },
        "cross_checks": {
            "decoded_xex_and_ghidra_call_sites_match": True,
            "bctrl_opcode": "0x4E800421",
            "call_sites_checked": len(ghidra_calls),
            "decoded_xex_and_ghidra_words_match": True,
            "words_checked": len(checked_words),
            "generated_mapping_exact_for_every_proved_target": True,
            "ghidra_xrefs": xref_evidence,
        },
        "original_frontier": {
            "generated_nodes_including_boundaries": len(original_generated),
            "descended_generated_nodes": len(original_active),
            "callable_imports": len(original_imports),
            "total_nodes": len(original_generated) + len(original_imports),
            "indirect_sites": 15,
            "interpretation": (
                "The existing path-insensitive direct closure is the seed. "
                "Proofs below are entry-context constraints, not general "
                "function-pointer type guesses."
            ),
        },
        "original_indirect_sites": site_rows,
        "table_evidence": table_summaries,
        "augmented_frontier": {
            "generated_nodes_including_opaque_boundaries": len(reached_generated),
            "opaque_boundary_nodes": len(
                reached_generated & frontier_module.BOUNDARIES),
            "descended_generated_nodes": len(active),
            "callable_import_nodes": len(reached_imports),
            "total_nodes_including_imports":
                len(reached_generated) + len(reached_imports),
            "new_generated_nodes": len(reached_generated - original_generated),
            "new_callable_imports": len(new_imports),
            "new_callable_import_symbols": sorted(new_imports),
            "callable_imports_by_library": dict(sorted(imports_by_library.items())),
            "reachable_callable_imports": sorted(reached_imports),
            "direct_call_sites_from_descended_nodes": len(direct_sites),
            "unique_direct_edges_from_descended_nodes": len(direct_edges),
            "unique_generated_direct_edges": len(generated_edges),
            "unique_callable_import_direct_edges": len(import_edges),
            "callable_import_direct_call_sites": sum(
                callee in callable_imports for _, callee in direct_sites),
            "proved_indirect_caller_target_edges": len(proved_edge_pairs),
            "syntactic_indirect_sites_in_descended_nodes": sum(
                indirect_counts[name] for name in active),
            "descended_nodes_with_indirect_dispatch": sum(
                indirect_counts[name] > 0 for name in active),
            "newly_exposed_indirect_sites": newly_exposed,
            "interpretation": (
                "Direct edges are followed transitively after admitting only "
                "the 254 caller/target edges proved for 10 of the original 15 "
                "sites. The two newly exposed sites are ledgered but deliberately "
                "not used as edges in this bounded pass."
            ),
        },
        "method_and_limits": {
            "title_code_executed": False,
            "path_sensitive_dynamic_execution_claimed": False,
            "decoded_data_rule": (
                "Decoded static words are admitted only after an independent "
                "read-only Ghidra read matches exactly and every non-null target "
                "has an exact generated address mapping."
            ),
            "constant_propagation_rule": (
                "Writable callback slots are admitted only where a dominating "
                "constant store is proved for every _xstart path reaching the "
                "site; general setter values remain unresolved."
            ),
            "tls_rule": (
                "The one TLS-return target relies on the exact prior "
                "KeTlsSetValue value and its success guard; an implementation "
                "must preserve XDK TLS semantics."
            ),
            "why_still_incomplete": (
                "Five original dynamic callbacks remain unbounded. Descending "
                "the proved constructor targets exposes two further indirect "
                "sites that require a separately validated second-wave proof."
            ),
        },
        "portme": [
            *[row["portme"] for row in unresolved_sites],
            *[row["portme"] for row in newly_exposed],
            (
                "PORTME: rerun this fixed-point process after each newly proved "
                "indirect edge; do not call the 30-import set complete yet."
            ),
            (
                "PORTME: preserve PPC/XDK ABI, TLS, callback ordering, imported "
                "data, and failure-path semantics before executing _xstart."
            ),
        ],
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_tsv.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    buffer = io.StringIO()
    fields = [
        "call_instruction_address", "return_address", "caller",
        "classification", "ctr_source", "proved_target_count",
        "proved_targets", "value_provenance", "portme",
    ]
    writer = csv.DictWriter(buffer, delimiter="\t", fieldnames=fields,
                            lineterminator="\n")
    writer.writeheader()
    for row in site_rows:
        writer.writerow({
            "call_instruction_address": row["call_instruction_address"],
            "return_address": row["return_address"],
            "caller": row["caller"],
            "classification": row["classification"],
            "ctr_source": row["ctr_source"],
            "proved_target_count": row["proved_target_count"],
            "proved_targets": ";".join(
                f"{target['address']}:{target['symbol']}"
                for target in row["proved_targets"]),
            "value_provenance": row["value_provenance"],
            "portme": row["portme"] or "",
        })
    output_tsv.write_text(buffer.getvalue(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
