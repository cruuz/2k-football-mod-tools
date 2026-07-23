#!/usr/bin/env python3
"""Repair only proved APF cross-function switch tails and ledger the residue.

This tool never edits the pinned XenonRecomp checkout or the baseline generated
corpus.  It derives a switch-table candidate, checks a separately generated
candidate corpus, and emits hashes/metadata rather than generated game code.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
from typing import Any, Iterable


SCHEMA = "apf2k8_static_recomp_switch_tail_dispatch/v1"
EXPECTED_XEX_PE_SHA256 = (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)
EXPECTED_VENDOR_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
EXPECTED_VENDOR_SOURCE_SHA256 = (
    "30e7ea5b4d8a225bc3e0ac71aebd1a0af7bcde5aaf5679517719b559c9cd777a"
)
IMAGE_BASE = 0x82000000
IMAGE_SIZE = 54_001_664
CODE_FIRST = 0x84630000
CODE_AFTER_LAST = 0x84D0904C

SWITCH_ERROR = re.compile(
    r"^ERROR: Switch case at ([0-9A-Fa-f]+) is trying to jump outside "
    r"function: ([0-9A-Fa-f]+)$"
)
MAPPING = re.compile(r"^\s*\{ 0x([0-9A-F]+), [^ }]+ \},$", re.MULTILINE)
IMPLEMENTATION = re.compile(
    r"^PPC_FUNC_IMPL\(__imp__sub_([0-9A-F]+)\) \{$", re.MULTILINE
)
RESOLVED_BLOCK = re.compile(
    r"^\s*// CROSS_FUNCTION_SWITCH_TAIL: exact mapped target 0x([0-9A-F]+)\n"
    r"\s*sub_([0-9A-F]+)\(ctx, base\);\n\s*return;$",
    re.MULTILINE,
)
PORTME_BLOCK = re.compile(
    r"^\s*// PORTME: unresolved cross-function switch target 0x([0-9A-F]+) "
    r"from bctr 0x([0-9A-F]+)\n\s*return;$",
    re.MULTILINE,
)


class DispatchError(RuntimeError):
    """Raised when a pinned input or candidate invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DispatchError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def pin(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def logical_pin(path: Path, logical_path: str) -> dict[str, Any]:
    row = pin(path)
    row["path"] = logical_path
    return row


def hex32(value: int) -> str:
    return f"0x{value:08X}"


def parse_errors(path: Path) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SWITCH_ERROR.match(line)
        if match:
            result.append(tuple(int(value, 16) for value in match.groups()))
    return result


def load_mappings(path: Path) -> set[int]:
    return {int(value, 16) for value in MAPPING.findall(path.read_text(encoding="utf-8"))}


def load_implementations(directory: Path) -> set[int]:
    result: set[int] = set()
    for path in directory.glob("ppc_recomp.*.cpp"):
        result.update(
            int(value, 16)
            for value in IMPLEMENTATION.findall(path.read_text(encoding="utf-8"))
        )
    return result


def load_instruction_counts(directory: Path) -> dict[int, int]:
    """Count decoded guest instructions in each generated sub implementation."""
    start = re.compile(r"^PPC_FUNC_IMPL\(__imp__sub_([0-9A-F]+)\) \{$")
    instruction = re.compile(r"^\t// ")
    result: dict[int, int] = {}
    for path in sorted(directory.glob("ppc_recomp.*.cpp")):
        current: int | None = None
        count = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            match = start.match(line)
            if match:
                current = int(match.group(1), 16)
                count = 0
            elif current is not None and line == "}":
                result[current] = count
                current = None
            elif current is not None and instruction.match(line):
                count += 1
    return result


def ledger_digest(paths: Iterable[Path]) -> str:
    state = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        data = path.read_bytes()
        state.update(path.name.encode("utf-8") + b"\0")
        state.update(len(data).to_bytes(8, "big"))
        state.update(hashlib.sha256(data).digest())
    return state.hexdigest()


def load_body_ranges(directory: Path) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            for body_range in row["body_ranges"]:
                ranges.append({
                    "first": int(body_range["start"], 16),
                    "last": int(body_range["end_inclusive"], 16),
                    "entry": int(row["address"], 16),
                    "name": row["name"],
                })
    return ranges


def owners(address: int, ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in ranges if row["first"] <= address <= row["last"]]


def decode_direct_branch(word: int, address: int) -> dict[str, Any] | None:
    # PowerPC I-form: opcode=18, LI is signed 26-bit (including low 00),
    # AA selects absolute/relative addressing, and LK distinguishes b from bl.
    if word >> 26 != 18:
        return None
    displacement = word & 0x03FFFFFC
    if displacement & 0x02000000:
        displacement -= 0x04000000
    absolute = bool(word & 2)
    link = bool(word & 1)
    target = displacement if absolute else address + displacement
    return {
        "mnemonic": "bl" if link else "b",
        "absolute": absolute,
        "link": link,
        "displacement": displacement,
        "target": target & 0xFFFFFFFF,
    }


def read_word(pe: bytes, address: int) -> int | None:
    offset = address - IMAGE_BASE
    if offset < 0 or offset + 4 > len(pe):
        return None
    return int.from_bytes(pe[offset:offset + 4], "big")


def render_switches(
    switches: list[dict[str, Any]], replacements: dict[int, int]
) -> str:
    parts = [
        "# Generated by apf_static_recomp_switch_tail_dispatch.py; "
        "Ghidra-body-gated terminal case fragments folded\n"
    ]
    for row in switches:
        parts.extend([
            "[[switch]]\n",
            f"base = 0x{int(row['base']):08X}\n",
            f"r = {int(row['r'])}\n",
            f"default = 0x{int(row['default']):08X}\n",
            "labels = [\n",
        ])
        for original in row["labels"]:
            label = replacements.get(int(original), int(original))
            if label == original:
                parts.append(f"    0x{label:08X},\n")
            else:
                parts.append(
                    f"    0x{label:08X}, # folded case entry 0x{int(original):08X}\n"
                )
        parts.extend(["]\n\n"])
    return "".join(parts)


def classify_target(
    target: int,
    bases: list[int],
    ranges: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], set[int]]:
    target_owners = owners(target, ranges)
    base_owner_entries = {
        row["entry"] for base in bases for row in owners(base, ranges)
    }
    target_owner_entries = {row["entry"] for row in target_owners}
    if not (CODE_FIRST <= target < CODE_AFTER_LAST):
        category = "outside_code_false_positive"
    elif target_owner_entries & base_owner_entries:
        category = "same_ghidra_body"
    elif target_owners:
        category = "other_ghidra_body"
    else:
        category = "no_ghidra_body"
    return category, target_owners, base_owner_entries


def candidate_cpp_text(directory: Path) -> str:
    return "".join(
        path.read_text(encoding="utf-8")
        for path in sorted(directory.glob("ppc_recomp.*.cpp"))
    )


def syntax_one(
    source: Path, compiler: str, include_paths: list[Path]
) -> dict[str, Any]:
    command = [compiler, "-std=c++20", "-O0", "-fsyntax-only"]
    command.extend(f"-I{path}" for path in include_paths)
    command.append(str(source))
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "name": source.name,
        "return_code": completed.returncode,
        "stdout_empty": completed.stdout == "",
        "stderr_empty": completed.stderr == "",
    }


def syntax_all(
    directory: Path,
    compiler: str,
    xenon_utils: Path,
    simde: Path,
    jobs: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sources = sorted(directory.glob("*.cpp"), key=lambda item: item.name)
    include_paths = [directory, xenon_utils, simde]
    outcomes: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        pending = {
            executor.submit(syntax_one, source, compiler, include_paths): source
            for source in sources
        }
        for future in as_completed(pending):
            outcomes.append(future.result())
    outcomes.sort(key=lambda row: str(row["name"]))
    failed = [row["name"] for row in outcomes if row["return_code"] != 0]
    noisy = [
        row["name"] for row in outcomes
        if not row["stdout_empty"] or not row["stderr_empty"]
    ]
    return outcomes, {
        "translation_unit_count": len(outcomes),
        "passed_count": len(outcomes) - len(failed),
        "failed_count": len(failed),
        "failed_translation_units": failed,
        "translation_units_with_output": noisy,
    }


def tree_summary(directory: Path) -> dict[str, Any]:
    files = sorted((path for path in directory.iterdir() if path.is_file()),
                   key=lambda item: item.name)
    state = hashlib.sha256()
    total = 0
    cpp_count = 0
    for path in files:
        size = path.stat().st_size
        digest = sha256_file(path)
        state.update(path.name.encode("utf-8") + b"\0")
        state.update(size.to_bytes(8, "big"))
        state.update(bytes.fromhex(digest))
        total += size
        cpp_count += path.suffix == ".cpp"
    return {
        "file_count": len(files),
        "cpp_file_count": cpp_count,
        "total_bytes": total,
        "tree_sha256": state.hexdigest(),
    }


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "target", "occurrence_count", "switch_bctr_bases", "classification",
        "raw_word", "direct_branch", "ghidra_target_owners", "portme",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pe", type=Path, required=True)
    parser.add_argument("--baseline-log", type=Path, required=True)
    parser.add_argument("--candidate-log", type=Path)
    parser.add_argument("--switches", type=Path, required=True)
    parser.add_argument("--recovered-switches", type=Path, required=True)
    parser.add_argument("--baseline-generated", type=Path, required=True)
    parser.add_argument("--candidate-generated", type=Path)
    parser.add_argument("--ledger-dir", type=Path, required=True)
    parser.add_argument("--vendor-root", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--candidate-config", type=Path, required=True)
    parser.add_argument("--xenon-utils", type=Path, required=True)
    parser.add_argument("--simde", type=Path, required=True)
    parser.add_argument("--compiler", default="clang++-18")
    parser.add_argument("--jobs", type=int, default=max(1, min(12, os.cpu_count() or 1)))
    parser.add_argument("--emit-only", action="store_true")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--tsv", type=Path)
    args = parser.parse_args()

    pe = args.pe.read_bytes()
    require(len(pe) == IMAGE_SIZE, "decompressed APF image size changed")
    require(sha256_bytes(pe) == EXPECTED_XEX_PE_SHA256,
            "decompressed APF image hash changed")
    require(pe[:2] == b"MZ", "decompressed APF image lost MZ header")

    vendor_commit = subprocess.run(
        ["git", "-C", str(args.vendor_root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    require(vendor_commit == EXPECTED_VENDOR_COMMIT, "vendored commit changed")
    vendor_source = args.vendor_root / "XenonRecomp/recompiler.cpp"
    require(sha256_file(vendor_source) == EXPECTED_VENDOR_SOURCE_SHA256,
            "pinned recompiler source changed")
    subprocess.run(
        ["git", "-C", str(args.vendor_root), "apply", "--check",
         str(args.patch.resolve())],
        capture_output=True, text=True, check=True,
    )

    baseline_errors = parse_errors(args.baseline_log)
    require(len(baseline_errors) == 3337, "baseline switch-error count changed")
    require(len({base for base, _ in baseline_errors}) == 196,
            "baseline switch-base count changed")
    require(len({target for _, target in baseline_errors}) == 806,
            "baseline unique-target count changed")

    mapping_path = args.baseline_generated / "ppc_func_mapping.cpp"
    mappings = load_mappings(mapping_path)
    implementations = load_implementations(args.baseline_generated)
    instruction_counts = load_instruction_counts(args.baseline_generated)
    implementation_total = sum(
        len(re.findall(r"^PPC_FUNC_IMPL\(", path.read_text(encoding="utf-8"),
                       re.MULTILINE))
        for path in args.baseline_generated.glob("*.cpp")
    )
    require(
        len(mappings) == 60731 and len(implementations) == 60160 and
        implementation_total == 60397,
        "baseline mapping/implementation counts changed",
    )
    mapped_targets = {target for _, target in baseline_errors if target in mappings}
    require(len(mapped_targets) == 570, "mapped switch-target count changed")
    require(mapped_targets <= implementations,
            "a mapped switch target lacks a generated implementation")
    mapped_occurrences = sum(target in mappings for _, target in baseline_errors)
    require(mapped_occurrences == 1998, "mapped switch occurrence count changed")

    # Secondary entries that are exactly one/two straight-line instructions
    # ending in blr can reuse a byte-identical generated function. Restrict the
    # two-instruction form to address-independent addi/lwz plus blr.
    terminal_sequences: dict[bytes, list[int]] = defaultdict(list)
    for address, count in instruction_counts.items():
        if address not in mappings or count not in (1, 2):
            continue
        offset = address - IMAGE_BASE
        if offset < 0 or offset + count * 4 > len(pe):
            continue
        sequence = pe[offset:offset + count * 4]
        words = [
            int.from_bytes(sequence[index:index + 4], "big")
            for index in range(0, len(sequence), 4)
        ]
        if words[-1] != 0x4E800020:
            continue
        if count == 2 and words[0] >> 26 not in {14, 32}:
            continue
        terminal_sequences[sequence].append(address)
    for addresses in terminal_sequences.values():
        addresses.sort()

    ranges = load_body_ranges(args.ledger_dir)
    require(ranges, "Ghidra body-range ledger is empty")
    by_target: dict[int, list[int]] = defaultdict(list)
    for base, target in baseline_errors:
        by_target[target].append(base)

    replacements: dict[int, int] = {}
    recovery_kinds: dict[int, str] = {}
    recovery_words: dict[int, list[int]] = {}
    target_details: dict[int, dict[str, Any]] = {}
    unresolved = sorted(set(by_target) - mappings)
    for target in unresolved:
        bases = sorted(set(by_target[target]))
        category, target_owners, base_owner_entries = classify_target(
            target, bases, ranges
        )
        word = read_word(pe, target)
        branch = decode_direct_branch(word, target) if word is not None else None
        common_owners = sorted(
            {row["entry"] for row in target_owners} & base_owner_entries
        )
        if (
            category == "same_ghidra_body" and branch is not None and
            not branch["link"] and int(branch["target"]) in mappings and
            int(branch["target"]) in implementations
        ):
            replacements[target] = int(branch["target"])
            recovery_kinds[target] = "direct_branch_to_exact_mapping"
            recovery_words[target] = [int(word)]
        elif category == "same_ghidra_body" and word is not None:
            offset = target - IMAGE_BASE
            sequence = b""
            if word == 0x4E800020:
                sequence = pe[offset:offset + 4]
            elif (
                offset + 8 <= len(pe) and
                int.from_bytes(pe[offset + 4:offset + 8], "big") == 0x4E800020 and
                word >> 26 in {14, 32}
            ):
                sequence = pe[offset:offset + 8]
            candidates = terminal_sequences.get(sequence, [])
            if candidates:
                replacements[target] = candidates[0]
                recovery_kinds[target] = "byte_identical_terminal_fragment"
                recovery_words[target] = [
                    int.from_bytes(sequence[index:index + 4], "big")
                    for index in range(0, len(sequence), 4)
                ]
        target_details[target] = {
            "target": target,
            "bases": bases,
            "occurrences": len(by_target[target]),
            "classification": category,
            "word": word,
            "branch": branch,
            "target_owners": target_owners,
            "common_owner_entries": common_owners,
        }

    branch_replacements = {
        source: destination for source, destination in replacements.items()
        if recovery_kinds[source] == "direct_branch_to_exact_mapping"
    }
    terminal_replacements = {
        source: destination for source, destination in replacements.items()
        if recovery_kinds[source] == "byte_identical_terminal_fragment"
    }
    require(branch_replacements == {
        0x8464A870: 0x849642B8,
        0x8493D600: 0x84946BB8,
        0x84ADB2D8: 0x84AD9F40,
    }, "conservative Ghidra/direct-branch recovery set changed")
    require(len(terminal_replacements) == 43,
            "byte-identical terminal-fragment recovery set changed")
    recovered_occurrences = sum(len(by_target[target]) for target in replacements)
    branch_recovered_occurrences = sum(
        len(by_target[target]) for target in branch_replacements
    )
    terminal_recovered_occurrences = sum(
        len(by_target[target]) for target in terminal_replacements
    )
    require(
        branch_recovered_occurrences == 10 and
        terminal_recovered_occurrences == 253 and
        recovered_occurrences == 263,
        "recovered occurrence count changed",
    )

    switch_document = tomllib.loads(args.switches.read_text(encoding="utf-8"))
    switches = switch_document["switch"]
    require(len(switches) == 970, "filtered switch-table count changed")
    rendered = render_switches(switches, replacements)
    args.recovered_switches.write_text(rendered, encoding="utf-8")

    bogus_rows = [
        row for row in switches
        if {0x2B0A000D, 0x554A502A, 0x7D4AD670} <= set(row["labels"])
    ]
    require(len(bogus_rows) == 1 and int(bogus_rows[0]["base"]) == 0x84B29BCC,
            "bogus switch-table identification changed")

    if args.emit_only:
        print(
            "APF_SWITCH_TAIL_RECOVERY_EMIT_PASS "
            f"unique={len(replacements)} occurrences={recovered_occurrences}"
        )
        return 0

    require(args.candidate_log is not None and args.candidate_generated is not None,
            "full mode requires candidate log and generated directory")
    require(args.json is not None and args.tsv is not None,
            "full mode requires JSON and TSV outputs")

    candidate_errors = parse_errors(args.candidate_log)
    expected_candidate_errors = [
        pair for pair in baseline_errors
        if pair[1] not in mappings and pair[1] not in replacements
    ]
    require(Counter(candidate_errors) == Counter(expected_candidate_errors),
            "candidate switch-error multiset is not the proved projection")
    require(len(candidate_errors) == 1076, "candidate error count changed")
    require(len({target for _, target in candidate_errors}) == 190,
            "candidate unique residue changed")

    candidate_text = candidate_cpp_text(args.candidate_generated)
    resolved_blocks = RESOLVED_BLOCK.findall(candidate_text)
    portme_blocks = PORTME_BLOCK.findall(candidate_text)
    require(len(resolved_blocks) == 2261,
            "candidate resolved tail-block count changed")
    require(all(left == right for left, right in resolved_blocks),
            "candidate tail call does not match its mapped target")
    require(len(portme_blocks) == 1076,
            "candidate address-specific PORTME count changed")
    require("// ERROR:" not in candidate_text,
            "candidate retained an anonymous switch ERROR comment")

    candidate_mappings = load_mappings(
        args.candidate_generated / "ppc_func_mapping.cpp"
    )
    candidate_implementations = load_implementations(args.candidate_generated)
    require(candidate_mappings == mappings and candidate_implementations == implementations,
            "candidate changed function mappings or implementations")

    compiler_path = Path(shutil.which(args.compiler) or "")
    require(compiler_path.is_file(), f"compiler not found: {args.compiler}")
    compiler_version = subprocess.run(
        [str(compiler_path), "--version"], capture_output=True, text=True, check=True
    ).stdout.splitlines()[0]
    outcomes, syntax = syntax_all(
        args.candidate_generated, args.compiler, args.xenon_utils,
        args.simde, args.jobs,
    )
    require(syntax == {
        "translation_unit_count": 237,
        "passed_count": 237,
        "failed_count": 0,
        "failed_translation_units": [],
        "translation_units_with_output": [],
    }, "candidate all-TU syntax gate failed")

    residue_targets = sorted({target for _, target in candidate_errors})
    residue_rows: list[dict[str, Any]] = []
    classification_counts: Counter[str] = Counter()
    classification_occurrences: Counter[str] = Counter()
    for target in residue_targets:
        detail = target_details[target]
        classification = str(detail["classification"])
        classification_counts[classification] += 1
        classification_occurrences[classification] += int(detail["occurrences"])
        branch = detail["branch"]
        direct_branch = ""
        if branch is not None:
            direct_branch = (
                f"{branch['mnemonic']}->{hex32(int(branch['target']))}"
            )
        owner_text = ",".join(
            f"{hex32(int(row['entry']))}:{row['name']}:"
            f"{hex32(int(row['first']))}-{hex32(int(row['last']))}"
            for row in detail["target_owners"]
        )
        portme = (
            f"// PORTME({hex32(target)}): recover and differentially validate "
            "this switch case entry before enabling native dispatch."
        )
        if classification == "outside_code_false_positive":
            portme = (
                f"// PORTME({hex32(target)}): reject/repair false-positive "
                "switch table 0x84B29BCC before native dispatch."
            )
        residue_rows.append({
            "target": hex32(target),
            "occurrence_count": detail["occurrences"],
            "switch_bctr_bases": ",".join(hex32(base) for base in detail["bases"]),
            "classification": classification,
            "raw_word": "" if detail["word"] is None else hex32(detail["word"]),
            "direct_branch": direct_branch,
            "ghidra_target_owners": owner_text,
            "portme": portme,
        })
    require(dict(classification_counts) == {
        "outside_code_false_positive": 3,
        "no_ghidra_body": 118,
        "same_ghidra_body": 69,
    }, "residue classification changed")
    require(dict(classification_occurrences) == {
        "outside_code_false_positive": 3,
        "no_ghidra_body": 825,
        "same_ghidra_body": 248,
    }, "residue occurrence classification changed")
    write_tsv(args.tsv, residue_rows)

    recovery_rows = []
    for source, destination in sorted(replacements.items()):
        detail = target_details[source]
        kind = recovery_kinds[source]
        if kind == "direct_branch_to_exact_mapping":
            proof = (
                "case entry and bctr share a Ghidra function body; the entry "
                "is one non-link direct branch to an exact generated mapping"
            )
        else:
            proof = (
                "case entry and bctr share a Ghidra function body; the one/two "
                "instruction straight-line fragment ends in blr and is byte-"
                "identical to the complete mapped replacement implementation"
            )
        recovery_rows.append({
            "case_entry": hex32(source),
            "recovery_kind": kind,
            "raw_words": [hex32(value) for value in recovery_words[source]],
            "mapped_replacement_entry": hex32(destination),
            "occurrence_count": detail["occurrences"],
            "switch_bctr_bases": [hex32(base) for base in detail["bases"]],
            "common_ghidra_owner_entries": [
                hex32(value) for value in detail["common_owner_entries"]
            ],
            "proof": proof,
        })

    baseline_log_lines = args.baseline_log.read_text(encoding="utf-8").splitlines()
    candidate_log_lines = args.candidate_log.read_text(encoding="utf-8").splitlines()
    require(baseline_log_lines[-1] == "Recompiling functions... 100%" and
            candidate_log_lines[-1] == "Recompiling functions... 100%",
            "a recompiler run did not reach 100%")

    report = {
        "schema": SCHEMA,
        "result": {
            "baseline_cross_function_switch_occurrences": 3337,
            "baseline_unique_switch_targets": 806,
            "exact_mapped_tail_dispatch_occurrences": 1998,
            "exact_mapped_unique_targets": 570,
            "ghidra_gated_branch_fold_occurrences": 10,
            "ghidra_gated_branch_fold_unique_targets": 3,
            "ghidra_gated_terminal_fragment_fold_occurrences": 253,
            "ghidra_gated_terminal_fragment_fold_unique_targets": 43,
            "candidate_tail_dispatch_occurrences": 2261,
            "remaining_portme_occurrences": 1076,
            "remaining_unique_targets": 190,
            "all_candidate_translation_units_syntax_passed": True,
            "whole_title_semantic_correctness_proved": False,
            "native_boot_proved": False,
        },
        "control_transfer_proof": {
            "bctr_updates_link_register": False,
            "candidate_sequence": "call exact generated entry; return",
            "existing_xenonrecomp_analogue": (
                "out-of-range non-link PPC b already uses call target; return"
            ),
            "candidate_lr_assignment_count_inside_resolved_blocks": 0,
            "scope": (
                "local guest control-transfer equivalence only; generated target "
                "semantics and the whole runtime remain independently unproved"
            ),
        },
        "recovered_case_entries": recovery_rows,
        "residue": {
            "unique_by_classification": dict(sorted(classification_counts.items())),
            "occurrences_by_classification": dict(
                sorted(classification_occurrences.items())
            ),
            "false_positive_switch": {
                "toml_base": "0x84B29BCC",
                "bctr_site": "0x84B29BE0",
                "invalid_targets": ["0x2B0A000D", "0x554A502A", "0x7D4AD670"],
                "state": "identified_not_silently_deleted",
            },
            "tsv": logical_pin(
                args.tsv,
                "reports/static_recomp/apf2k8_static_recomp_switch_tail_residue.tsv",
            ),
        },
        "candidate_generated_tree": tree_summary(args.candidate_generated),
        "syntax_gate": {
            **syntax,
            "compiler_requested": args.compiler,
            "compiler_resolved": compiler_path.resolve().as_posix(),
            "compiler_version_first_line": compiler_version,
            "compiler_binary_sha256": sha256_file(compiler_path.resolve()),
            "flags": ["-std=c++20", "-O0", "-fsyntax-only"],
            "outcomes": outcomes,
        },
        "sources": {
            "apf_memory_image": logical_pin(
                args.pe, "temporary decompressed APF PE memory image"
            ),
            "baseline_log": pin(args.baseline_log),
            "candidate_log": pin(args.candidate_log),
            "filtered_switches": pin(args.switches),
            "recovered_switches": logical_pin(
                args.recovered_switches,
                "reports/static_recomp/apf2k8_xenon_switch_tables_switch_tail_candidate.toml",
            ),
            "baseline_mapping": pin(mapping_path),
            "candidate_patch": pin(args.patch),
            "candidate_config": pin(args.candidate_config),
            "vendor_recompiler_source": pin(vendor_source),
            "vendor_commit": vendor_commit,
            "ghidra_ledger_file_count": len(list(args.ledger_dir.glob("*.jsonl"))),
            "ghidra_ledger_corpus_sha256": ledger_digest(
                args.ledger_dir.glob("*.jsonl")
            ),
            "generator": pin(Path(__file__)),
        },
        "portme": [row["portme"] for row in residue_rows],
    }
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    print(
        "APF_STATIC_RECOMP_SWITCH_TAIL_DISPATCH_PASS "
        "baseline=3337 resolved=2261 remaining=1076 unique_remaining=190 "
        "syntax=237/237 semantics=partial runtime=no"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
