#!/usr/bin/env python3
"""Syntax-check every APF XenonRecomp C++ translation unit with Clang 18.

The JSON output contains hashes, sizes, compiler results, and normalized
diagnostics only. It never copies generated source text into the report.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import time
from typing import Any


SCHEMA = "apf2k8_static_recomp_all_tus/v1"
EXPECTED_VENDOR_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
EXPECTED_TU_COUNT = 237
EXPECTED_NUMBERED_TU_COUNT = 236
EXPECTED_CPP_MANIFEST_SHA256 = "5e90f504e1291e3bcc2ba2e3688da07d44ba7b7bfbf10ac62beffb48d1e79132"
EXPECTED_GENERATED_TREE_SHA256 = "6ac280d3fa0c6f016011ff176089ddbee4df4077c366a69623d9556db0e54599"

DIAGNOSTIC = re.compile(
    r"^(.*?):(\d+):(\d+):\s+(fatal error|error|warning|note):\s+(.*)$"
)
NUMBERED_TU = re.compile(r"^ppc_recomp\.(\d+)\.cpp$")


class CheckError(RuntimeError):
    """Raised when the pinned corpus or compiler environment changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def expected_names() -> list[str]:
    return ["ppc_func_mapping.cpp"] + [
        f"ppc_recomp.{index}.cpp" for index in range(EXPECTED_NUMBERED_TU_COUNT)
    ]


def manifest_digest(rows: list[dict[str, Any]]) -> str:
    state = hashlib.sha256()
    for row in rows:
        state.update(str(row["name"]).encode("utf-8") + b"\0")
        state.update(int(row["size"]).to_bytes(8, "big"))
        state.update(bytes.fromhex(str(row["sha256"])))
    return state.hexdigest()


def generated_tree_digest(directory: Path) -> str:
    files = sorted((item for item in directory.iterdir() if item.is_file()),
                   key=lambda item: item.name)
    state = hashlib.sha256()
    for item in files:
        size = item.stat().st_size
        state.update(item.name.encode("utf-8") + b"\0")
        state.update(size.to_bytes(8, "big"))
        state.update(bytes.fromhex(sha256_file(item)))
    return state.hexdigest()


def normalize_diagnostics(stderr: str, source: Path) -> list[dict[str, Any]]:
    """Retain compiler classifications, but never generated source excerpts."""
    diagnostics: list[dict[str, Any]] = []
    for line in stderr.splitlines():
        match = DIAGNOSTIC.match(line)
        if not match:
            continue
        path_text, line_no, column, severity, message = match.groups()
        diagnostics.append({
            "source": source.name if Path(path_text).name == source.name
            else Path(path_text).name,
            "line": int(line_no),
            "column": int(column),
            "severity": severity,
            "message": message,
        })
    return diagnostics


def syntax_check(
    source: Path,
    compiler: str,
    flags: list[str],
    include_paths: list[Path],
) -> dict[str, Any]:
    command = [compiler, *flags]
    command.extend(f"-I{path}" for path in include_paths)
    command.append(str(source))
    start = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True,
                               check=False)
    elapsed = time.perf_counter() - start
    diagnostics = normalize_diagnostics(completed.stderr, source)
    severity_counts = Counter(row["severity"] for row in diagnostics)
    unparsed_stderr = bool(completed.stderr.strip()) and not diagnostics
    return {
        "name": source.name,
        "return_code": completed.returncode,
        "stdout_empty": completed.stdout == "",
        "stderr_empty": completed.stderr == "",
        "diagnostic_counts": dict(sorted(severity_counts.items())),
        "first_diagnostics": diagnostics[:3],
        "unparsed_stderr": unparsed_stderr,
        # Per-TU elapsed time is deliberately internal and omitted from JSON.
        "_elapsed_seconds": elapsed,
    }


def timing_summary(paths: list[Path], root: Path) -> dict[str, Any]:
    if not paths:
        return {
            "assessed": False,
            "stable": None,
            "canonical_measurements": [],
            "reason": "no frozen timing observations were supplied",
        }
    observations: list[dict[str, Any]] = []
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        require(
            document.get("schema") ==
            "apf2k8_static_recomp_all_tus_timing_observation/v1",
            f"invalid timing observation schema: {path}",
        )
        require(document.get("translation_unit_count") == EXPECTED_TU_COUNT,
                f"timing observation TU count changed: {path}")
        observations.append({
            "path": relative(path, root),
            "jobs": int(document["jobs"]),
            "wall_seconds": float(document["wall_seconds"]),
            "child_user_cpu_seconds": float(
                document["child_user_cpu_seconds"]
            ),
            "child_system_cpu_seconds": float(
                document["child_system_cpu_seconds"]
            ),
            "child_total_cpu_seconds": float(
                document["child_total_cpu_seconds"]
            ),
        })
    require(len(observations) >= 2,
            "at least two observations are required to assess timing stability")
    require(len({row["jobs"] for row in observations}) == 1,
            "timing observations used different worker counts")

    def summarize(key: str) -> dict[str, Any]:
        values = [float(row[key]) for row in observations]
        mean = sum(values) / len(values)
        relative_span = (max(values) - min(values)) / mean
        return {
            "minimum": round(min(values), 6),
            "maximum": round(max(values), 6),
            "mean": round(mean, 6),
            "relative_span": round(relative_span, 6),
        }

    wall = summarize("wall_seconds")
    total_cpu = summarize("child_total_cpu_seconds")
    threshold = 0.05
    stable = (
        float(wall["relative_span"]) <= threshold
        and float(total_cpu["relative_span"]) <= threshold
    )
    return {
        "assessed": True,
        "stable": stable,
        "stability_threshold_relative_span": threshold,
        "observation_count": len(observations),
        "jobs": observations[0]["jobs"],
        "wall_seconds": wall,
        "child_user_cpu_seconds": summarize("child_user_cpu_seconds"),
        "child_system_cpu_seconds": summarize("child_system_cpu_seconds"),
        "child_total_cpu_seconds": total_cpu,
        "canonical_measurements": observations,
        "interpretation": (
            "Frozen observations characterize this host run only; timing is not "
            "an acceptance invariant for syntax correctness."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--generated", type=Path,
        default=Path("build-static-recomp-apf/ppc-filtered"),
    )
    parser.add_argument(
        "--vendor-root", type=Path,
        default=Path("tools/vendor/XenonRecomp"),
    )
    parser.add_argument("--clang", default="clang++-18")
    parser.add_argument("--jobs", type=int, default=min(12, os.cpu_count() or 1))
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument(
        "--timing-baseline", type=Path, action="append", default=[],
        help="Frozen noncanonical timing observation; repeat at least twice",
    )
    parser.add_argument(
        "--timing-json", type=Path,
        help="Optional noncanonical timing observation for stability assessment",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    generated = (root / args.generated).resolve() if not args.generated.is_absolute() \
        else args.generated.resolve()
    vendor = (root / args.vendor_root).resolve() if not args.vendor_root.is_absolute() \
        else args.vendor_root.resolve()
    require(args.jobs > 0, "--jobs must be positive")
    require(generated.is_dir(), "generated C++ directory is missing")
    require(vendor.is_dir(), "vendored XenonRecomp directory is missing")

    compiler_lookup = shutil.which(args.clang)
    require(compiler_lookup is not None, f"compiler not found: {args.clang}")
    compiler_path = Path(compiler_lookup).resolve()
    version_lines = subprocess.run(
        [args.clang, "--version"], capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    require(version_lines and "clang version 18.1.3" in version_lines[0],
            "expected pinned Clang 18.1.3")

    vendor_commit = subprocess.run(
        ["git", "-C", str(vendor), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    require(vendor_commit == EXPECTED_VENDOR_COMMIT,
            "vendored XenonRecomp commit changed")

    sources_by_name = {
        item.name: item for item in generated.iterdir()
        if item.is_file() and item.suffix == ".cpp"
    }
    names = expected_names()
    require(sorted(sources_by_name) == sorted(names),
            "generated translation-unit roster changed")
    numbered = sorted(
        int(match.group(1)) for name in sources_by_name
        if (match := NUMBERED_TU.match(name))
    )
    require(numbered == list(range(EXPECTED_NUMBERED_TU_COUNT)),
            "numbered translation units are not contiguous 0..235")

    manifest: list[dict[str, Any]] = []
    for name in names:
        source = sources_by_name[name]
        manifest.append({
            "name": name,
            "size": source.stat().st_size,
            "sha256": sha256_file(source),
        })
    manifest_sha256 = manifest_digest(manifest)
    require(manifest_sha256 == EXPECTED_CPP_MANIFEST_SHA256,
            "generated C++ manifest changed")
    tree_sha256 = generated_tree_digest(generated)
    require(tree_sha256 == EXPECTED_GENERATED_TREE_SHA256,
            "complete generated output tree changed")

    xenon_utils = vendor / "XenonUtils"
    simde = vendor / "thirdparty" / "simde"
    include_paths = [generated, xenon_utils, simde]
    for include in include_paths:
        require(include.is_dir(), f"include directory missing: {include}")
    header_paths = [
        generated / "ppc_config.h",
        generated / "ppc_recomp_shared.h",
        xenon_utils / "ppc_context.h",
    ]
    for header in header_paths:
        require(header.is_file(), f"required header missing: {header}")

    flags = ["-std=c++20", "-O0", "-fsyntax-only"]
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    wall_start = time.perf_counter()
    outcomes_by_name: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {
            executor.submit(
                syntax_check, sources_by_name[name], args.clang, flags,
                include_paths,
            ): name for name in names
        }
        for future in as_completed(futures):
            outcome = future.result()
            outcomes_by_name[str(outcome["name"])] = outcome
    wall_seconds = time.perf_counter() - wall_start
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    user_cpu = usage_after.ru_utime - usage_before.ru_utime
    system_cpu = usage_after.ru_stime - usage_before.ru_stime

    outcomes: list[dict[str, Any]] = []
    individual_elapsed = 0.0
    for name in names:
        outcome = outcomes_by_name[name]
        individual_elapsed += float(outcome.pop("_elapsed_seconds"))
        outcomes.append(outcome)

    failures = [row for row in outcomes if row["return_code"] != 0]
    passes = len(outcomes) - len(failures)
    diagnostics = Counter()
    for row in outcomes:
        diagnostics.update(row["diagnostic_counts"])
    unparsed_stderr_count = sum(bool(row["unparsed_stderr"]) for row in outcomes)
    timing_paths = [
        path.resolve() if path.is_absolute() else (root / path).resolve()
        for path in args.timing_baseline
    ]
    timing = timing_summary(timing_paths, root)
    if timing["assessed"]:
        require(timing["jobs"] == args.jobs,
                "timing baseline worker count differs from this run")

    report = {
        "schema": SCHEMA,
        "result": {
            "translation_unit_count": len(outcomes),
            "passed_count": passes,
            "failed_count": len(failures),
            "all_translation_units_passed": not failures,
            "syntax_only": True,
            "semantic_correctness_proved": False,
            "link_success_proved": False,
            "runtime_or_native_boot_proved": False,
        },
        "compiler": {
            "requested": args.clang,
            "resolved_path": str(compiler_path),
            "binary_sha256": sha256_file(compiler_path),
            "version_first_line": version_lines[0],
            "flags": flags,
            "include_paths": [relative(path, root) for path in include_paths],
        },
        "inputs": {
            "vendor_commit": vendor_commit,
            "complete_generated_tree_sha256": tree_sha256,
            "cpp_manifest_sha256": manifest_sha256,
            "cpp_total_bytes": sum(int(row["size"]) for row in manifest),
            "translation_units": manifest,
            "headers": [
                {
                    "path": relative(path, root),
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for path in header_paths
            ],
        },
        "diagnostics": {
            "counts_by_severity": dict(sorted(diagnostics.items())),
            "translation_units_with_unparsed_stderr": unparsed_stderr_count,
            "failing_translation_units": [
                {
                    "name": row["name"],
                    "return_code": row["return_code"],
                    "diagnostic_counts": row["diagnostic_counts"],
                    "first_diagnostics": row["first_diagnostics"],
                    "unparsed_stderr": row["unparsed_stderr"],
                }
                for row in failures
            ],
        },
        "outcomes": outcomes,
        "timing": timing,
        "interpretation": (
            "All-pass syntax checking proves only that Clang 18 can parse each "
            "generated translation unit independently with the pinned headers. "
            "It does not prove PPC semantics, cross-TU linking, a title runtime, "
            "or native APF boot/gameplay."
        ),
    }

    output_path = args.json if args.json.is_absolute() else root / args.json
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")

    if args.timing_json:
        timing_path = args.timing_json if args.timing_json.is_absolute() \
            else root / args.timing_json
        timing = {
            "schema": "apf2k8_static_recomp_all_tus_timing_observation/v1",
            "jobs": args.jobs,
            "translation_unit_count": len(outcomes),
            "wall_seconds": round(wall_seconds, 6),
            "child_user_cpu_seconds": round(user_cpu, 6),
            "child_system_cpu_seconds": round(system_cpu, 6),
            "child_total_cpu_seconds": round(user_cpu + system_cpu, 6),
            "sum_individual_wall_seconds": round(individual_elapsed, 6),
            "canonical": False,
        }
        timing_path.parent.mkdir(parents=True, exist_ok=True)
        timing_path.write_text(json.dumps(timing, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")

    print(
        "APF_STATIC_RECOMP_ALL_TUS_CHECK "
        f"total={len(outcomes)} passed={passes} failed={len(failures)} "
        f"diagnostics={sum(diagnostics.values())}"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
