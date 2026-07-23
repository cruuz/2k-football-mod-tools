#!/usr/bin/env python3
"""Create an isolated APF corpus with a fail-closed per-instruction hook.

The input is never edited.  The postprocessor first proves that the derived
corpus preserves the pinned XenonRecomp function and guest-instruction marker
stream, then injects exactly one budget step immediately after every marker.
Any source construct that cannot be tied back to that stream is rejected.
This tool does not compile or call translated title code.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable


SCHEMA = "apf2k8_guest_instruction_budget_instrumentation/v1"
NUMBERED_SOURCE_COUNT = 236
EXPECTED_FUNCTION_COUNT = 60_397
EXPECTED_INSTRUCTION_OCCURRENCES = 1_808_124
EXPECTED_MAPPING_COUNT = 60_731
EXPECTED_SUPPORT_FILES = (
    "ppc_config.h",
    "ppc_context.h",
    "ppc_recomp_shared.h",
    "ppc_func_mapping.cpp",
)
INSTRUMENTATION_HEADER = (
    '#include "static_runtime/apf_guest_instruction_budget.h"\n'
)
HOOK_NAME = "VC_APF_GUEST_INSTRUCTION_STEP"
FUNCTION_RE = re.compile(
    r"^PPC_FUNC_IMPL\((__imp__[A-Za-z0-9_]+)\) \{$"
)
MAPPING_RE = re.compile(
    r"^\s*\{ 0x([0-9A-Fa-f]+), ([A-Za-z0-9_]+) \},$"
)
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):$")
GOTO_RE = re.compile(r"\bgoto loc_([0-9A-F]{8});")
DECLARATION_RE = re.compile(
    r"^\t(?:PPCRegister|PPCVRegister|bool|float|double|"
    r"u?int(?:8|16|32|64)_t) [A-Za-z_][A-Za-z0-9_]*\{\};$"
)
HOOK_RE = re.compile(
    r"^\tVC_APF_GUEST_INSTRUCTION_STEP\(0x([0-9A-F]{8})u\);$"
)
CODE_BASE = 0x84630000
CODE_END_EXCLUSIVE = 0x84D0904C


class InstrumentationError(RuntimeError):
    """Raised when a source/provenance invariant cannot be proved."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InstrumentationError(message)


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def expected_roster(directory: Path) -> list[Path]:
    return [directory / name for name in EXPECTED_SUPPORT_FILES] + [
        directory / f"ppc_recomp.{index}.cpp"
        for index in range(NUMBERED_SOURCE_COUNT)
    ]


def exact_roster(directory: Path) -> list[Path]:
    require(directory.is_dir(), f"corpus directory is missing: {directory}")
    expected = expected_roster(directory)
    entries = sorted(directory.iterdir())
    require(all(path.is_file() and not path.is_symlink() for path in entries),
            f"corpus contains a directory/symlink/non-regular entry: "
            f"{directory}")
    actual = entries
    require(all(path.is_file() and not path.is_symlink() for path in expected),
            f"corpus has a missing/non-regular required file: {directory}")
    require({path.name for path in actual} == {path.name for path in expected},
            f"corpus roster changed: {directory}")
    return sorted(expected, key=lambda path: path.name)


def tree_sha256(directory: Path, roster: Iterable[Path]) -> str:
    state = hashlib.sha256()
    for path in sorted(roster, key=lambda item: item.name):
        name = path.relative_to(directory).as_posix().encode("utf-8")
        data = path.read_bytes()
        state.update(len(name).to_bytes(4, "big"))
        state.update(name)
        state.update(len(data).to_bytes(8, "big"))
        state.update(data)
    return state.hexdigest()


def parse_mappings(path: Path) -> dict[str, int]:
    mappings: dict[str, int] = {}
    addresses: set[int] = set()
    for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1):
        match = MAPPING_RE.match(line)
        if match is None:
            continue
        address = int(match.group(1), 16)
        symbol = match.group(2)
        require(symbol not in mappings,
                f"duplicate mapping symbol {symbol} at {path}:{line_number}")
        require(address not in addresses,
                f"duplicate mapping address 0x{address:08X}")
        mappings[symbol] = address
        addresses.add(address)
    require(len(mappings) == EXPECTED_MAPPING_COUNT,
            f"mapping count changed: {len(mappings)}")
    return mappings


@dataclass(frozen=True)
class InstructionMarker:
    implementation_symbol: str
    host_symbol: str
    address: int
    comment: str


@dataclass
class ParsedSource:
    markers: list[InstructionMarker]
    function_symbols: list[str]
    label_count: int
    goto_count: int
    prologue_count: int


def parse_source(path: Path, mappings: dict[str, int]) -> ParsedSource:
    text = path.read_text(encoding="utf-8")
    require("\r" not in text and text.endswith("\n"),
            f"source is not canonical LF-terminated UTF-8: {path}")
    require(HOOK_NAME not in text and INSTRUMENTATION_HEADER.strip() not in text,
            f"input is already instrumented: {path}")

    markers: list[InstructionMarker] = []
    functions: list[str] = []
    current_impl: str | None = None
    current_host: str | None = None
    current_start = 0
    current_marker_count = 0
    current_prologue_count = 0
    current_saw_marker = False
    label_count = 0
    goto_count = 0
    prologue_count = 0
    function_labels: set[int] = set()
    function_gotos: list[tuple[int, int]] = []

    def finish_function(line_number: int) -> None:
        nonlocal current_impl, current_host, current_start
        nonlocal current_marker_count, current_prologue_count
        nonlocal current_saw_marker, function_labels, function_gotos
        if current_impl is None:
            return
        require(current_prologue_count == 1,
                f"function {current_impl} has {current_prologue_count} "
                f"prologues before {path}:{line_number}")
        require(current_marker_count > 0,
                f"function {current_impl} has no guest instruction marker")
        missing_targets = [
            (target, source_line) for target, source_line in function_gotos
            if target not in function_labels
        ]
        require(not missing_targets,
                f"goto target lacks an audited instruction label in "
                f"{current_impl}: {missing_targets[:3]}")
        current_impl = None
        current_host = None
        current_start = 0
        current_marker_count = 0
        current_prologue_count = 0
        current_saw_marker = False
        function_labels = set()
        function_gotos = []

    lines = text.splitlines()
    for line_number, line in enumerate(lines, 1):
        function_match = FUNCTION_RE.match(line)
        if function_match is not None:
            require(current_impl is None,
                    f"nested/unclosed function before {path}:{line_number}")
            current_impl = function_match.group(1)
            current_host = current_impl.removeprefix("__imp__")
            require(current_host in mappings,
                    f"function mapping missing for {current_impl}")
            current_start = mappings[current_host]
            if current_host.startswith("sub_"):
                require(int(current_host[4:], 16) == current_start,
                        f"encoded function address changed for {current_host}")
            require(CODE_BASE <= current_start < CODE_END_EXCLUSIVE and
                    (current_start & 3) == 0,
                    f"function start is outside the translated code range: "
                    f"{current_host}=0x{current_start:08X}")
            require(current_impl not in functions,
                    f"duplicate generated function: {current_impl}")
            functions.append(current_impl)
            continue

        if current_impl is None:
            require(not is_instruction_marker(line),
                    f"guest marker outside a function at {path}:{line_number}")
            continue

        if line == "}":
            finish_function(line_number)
            continue
        if line == "\tPPC_FUNC_PROLOGUE();":
            require(not current_saw_marker,
                    f"late function prologue at {path}:{line_number}")
            current_prologue_count += 1
            prologue_count += 1
            continue

        label_match = LABEL_RE.match(line)
        if label_match is not None:
            address = int(label_match.group(1), 16)
            expected = current_start + current_marker_count * 4
            require(address == expected,
                    f"non-sequential label {line} expected loc_{expected:08X} "
                    f"at {path}:{line_number}")
            label_count += 1
            function_labels.add(address)
            continue

        if line and not line.startswith(("\t", " ")) and line.endswith(":"):
            raise InstrumentationError(
                f"unrecognized control-flow label at {path}:{line_number}: "
                f"{line!r}")

        if is_instruction_marker(line):
            require(current_prologue_count == 1,
                    f"marker before exact prologue at {path}:{line_number}")
            address = current_start + current_marker_count * 4
            require(CODE_BASE <= address < CODE_END_EXCLUSIVE and
                    (address & 3) == 0,
                    f"instruction address escaped code range at "
                    f"{path}:{line_number}")
            markers.append(InstructionMarker(
                current_impl, current_host, address, line[4:]))
            current_marker_count += 1
            current_saw_marker = True
            continue

        if not current_saw_marker and line:
            require(DECLARATION_RE.match(line) is not None,
                    f"un-instrumentable code before first marker at "
                    f"{path}:{line_number}: {line!r}")

        if "goto" in line:
            targets = [int(value, 16) for value in GOTO_RE.findall(line)]
            require(len(targets) == 1,
                    f"unrecognized/computed goto at {path}:{line_number}")
            function_gotos.append((targets[0], line_number))
            goto_count += 1

    require(current_impl is None, f"unterminated function at EOF: {path}")
    require(len(functions) == len(set(functions)),
            f"function roster is not unique: {path}")
    return ParsedSource(markers, functions, label_count, goto_count,
                        prologue_count)


def is_instruction_marker(line: str) -> bool:
    """Recognize XenonRecomp's one-tab instruction comments.

    A one-tab ``ERROR`` is translator control-flow residue belonging to the
    preceding branch instruction; it is not an additional guest instruction.
    Candidate-added switch diagnostics are indented two tabs and likewise are
    not markers.  The exact marker stream is independently compared with the
    pinned baseline, so an unknown one-tab annotation fails that comparison.
    """
    return (line.startswith("\t// ") and
            not line.startswith(("\t// ERROR ", "\t// PORTME(")))


def update_marker_manifest(state: Any, source_name: str,
                           marker: InstructionMarker) -> None:
    for value in (
        source_name,
        marker.implementation_symbol,
        marker.host_symbol,
        f"{marker.address:08X}",
        marker.comment,
    ):
        encoded = value.encode("utf-8")
        state.update(len(encoded).to_bytes(4, "big"))
        state.update(encoded)


def instrument_source(source: Path, output: Path,
                      parsed: ParsedSource,
                      mappings: dict[str, int]) -> tuple[int, str]:
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    require(lines and lines[0] == '#include "ppc_recomp_shared.h"\n',
            f"generated include prefix changed: {source}")
    transformed = [lines[0], INSTRUMENTATION_HEADER]
    current_host: str | None = None
    current_start = 0
    current_marker_count = 0
    hooks = 0

    for line in lines[1:]:
        stripped = line.rstrip("\n")
        function_match = FUNCTION_RE.match(stripped)
        if function_match is not None:
            implementation = function_match.group(1)
            current_host = implementation.removeprefix("__imp__")
            current_start = mappings[current_host]
            current_marker_count = 0
        transformed.append(line)
        if is_instruction_marker(line):
            require(current_host is not None,
                    f"marker lost function ownership while writing {source}")
            address = current_start + current_marker_count * 4
            transformed.append(
                f"\t{HOOK_NAME}(0x{address:08X}u);\n")
            current_marker_count += 1
            hooks += 1

    require(hooks == len(parsed.markers),
            f"hook count mismatch while writing {source}")
    output.write_text("".join(transformed), encoding="utf-8", newline="")
    return hooks, sha256_file(output)


def audit_instrumented(source: Path, output: Path,
                       markers: list[InstructionMarker]) -> tuple[int, str]:
    source_text = source.read_text(encoding="utf-8")
    output_text = output.read_text(encoding="utf-8")
    lines = output_text.splitlines(keepends=True)
    require(lines.count(INSTRUMENTATION_HEADER) == 1,
            f"instrumentation header count changed: {output}")
    hook_lines = [line for line in lines if HOOK_NAME in line]
    require(len(hook_lines) == len(markers),
            f"instrumented hook count changed: {output}")

    marker_index = 0
    recovered: list[str] = []
    for index, line in enumerate(lines):
        if line == INSTRUMENTATION_HEADER:
            continue
        hook_match = HOOK_RE.match(line.rstrip("\n"))
        if hook_match is not None:
            require(index > 0 and is_instruction_marker(
                        lines[index - 1].rstrip("\n")),
                    f"hook does not immediately follow marker: "
                    f"{output}:{index + 1}")
            require(marker_index < len(markers),
                    f"extra hook at {output}:{index + 1}")
            address = int(hook_match.group(1), 16)
            require(address == markers[marker_index].address,
                    f"hook address mismatch at {output}:{index + 1}")
            marker_index += 1
            continue
        require(HOOK_NAME not in line,
                f"malformed hook token at {output}:{index + 1}")
        recovered.append(line)
    require(marker_index == len(markers),
            f"not every marker was audited in {output}")
    recovered_text = "".join(recovered)
    require(recovered_text == source_text,
            f"de-instrumentation does not recover exact input: {output}")

    hook_manifest = hashlib.sha256()
    for marker in markers:
        update_marker_manifest(hook_manifest, output.name, marker)
    return marker_index, hook_manifest.hexdigest()


def load_manifest(path: Path | None, root: Path, source: Path,
                  source_roster: list[Path]) -> dict[str, Any] | None:
    if path is None:
        return None
    require(path.is_file() and not path.is_symlink(),
            f"source manifest is missing/non-regular: {path}")
    item: dict[str, Any] = {
        "path": relative(path, root),
        "sha256": sha256_file(path),
    }
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        require(isinstance(data, dict), "source manifest JSON is not an object")
        item["schema"] = data.get("schema")
        if data.get("schema") == \
                "apf2k8_static_recomp_opcode_switch_composed/v1":
            generated = data.get("generated_corpus")
            result = data.get("result")
            require(isinstance(generated, dict) and isinstance(result, dict),
                    "composed-corpus manifest structure changed")
            declared_path = (root / generated["path"]).resolve()
            require(declared_path == source and
                    generated.get("file_count") == len(source_roster) and
                    result.get("single_composed_derived_corpus_exists") is True and
                    result.get("opcode_candidate_included") is True and
                    result.get("switch_tail_candidate_included") is True and
                    result.get("title_entry_called") is False,
                    "composed-corpus manifest does not bind this safe input")
            declared_files = generated.get("files")
            require(isinstance(declared_files, list) and
                    len(declared_files) == len(source_roster),
                    "composed-corpus file manifest changed")
            declared_by_name = {entry["name"]: entry
                                for entry in declared_files}
            require(len(declared_by_name) == len(source_roster),
                    "composed-corpus manifest has duplicate file names")
            for source_file in source_roster:
                declared = declared_by_name.get(source_file.name)
                require(declared is not None and
                        declared.get("size") == source_file.stat().st_size and
                        declared.get("sha256") == sha256_file(source_file),
                        f"source file differs from composed manifest: "
                        f"{source_file.name}")
            item["corpus_binding_verified"] = True
            item["declared_tree_sha256"] = generated.get("tree_sha256")
            item["declared_cpp_manifest_sha256"] = \
                generated.get("cpp_manifest_sha256")
        else:
            item["corpus_binding_verified"] = False
    return item


def write_exclusive(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--input", type=Path, required=True,
                        help="read-only derived XenonRecomp corpus")
    parser.add_argument("--baseline", type=Path, default=Path(
        "build-static-recomp-apf/ppc-filtered"))
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--expected-input-tree-sha256")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    resolve = lambda path: path.resolve() if path.is_absolute() else \
        (root / path).resolve()
    source = resolve(args.input)
    baseline = resolve(args.baseline)
    output = resolve(args.output)
    report_path = resolve(args.json)
    manifest_path = resolve(args.source_manifest) \
        if args.source_manifest is not None else None

    require(source != baseline and output != source and output != baseline,
            "input, baseline, and output must be distinct")
    require(output not in source.parents and source not in output.parents,
            "output must not contain/be contained by input")
    require(output not in baseline.parents and baseline not in output.parents,
            "output must not contain/be contained by baseline")
    require(not output.exists() and not output.is_symlink(),
            f"output already exists: {output}")
    require(not report_path.exists() and not report_path.is_symlink(),
            f"report already exists: {report_path}")

    source_roster = exact_roster(source)
    baseline_roster = exact_roster(baseline)
    source_tree = tree_sha256(source, source_roster)
    baseline_tree = tree_sha256(baseline, baseline_roster)
    if args.expected_input_tree_sha256 is not None:
        require(source_tree == args.expected_input_tree_sha256.lower(),
                "derived input tree hash does not match caller pin")
    manifest = load_manifest(manifest_path, root, source, source_roster)

    changed_support_files = [
        name for name in EXPECTED_SUPPORT_FILES
        if (source / name).read_bytes() != (baseline / name).read_bytes()
    ]
    require(set(changed_support_files) <= {"ppc_context.h"},
            "derived corpus unexpectedly changed mapping/config/shared support")
    if changed_support_files:
        require(manifest is not None and
                manifest.get("corpus_binding_verified") is True,
                "patched opcode context lacks an exact bound source manifest")
    mappings = parse_mappings(source / "ppc_func_mapping.cpp")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(
        prefix=f".{output.name}.instrumenting-", dir=output.parent))
    renamed = False
    marker_manifest = hashlib.sha256()
    hook_manifest = hashlib.sha256()
    unique_addresses: set[int] = set()
    per_file: list[dict[str, Any]] = []
    total_functions = 0
    total_markers = 0
    total_hooks = 0
    total_labels = 0
    total_gotos = 0
    try:
        for name in EXPECTED_SUPPORT_FILES:
            shutil.copyfile(source / name, temporary / name)

        for index in range(NUMBERED_SOURCE_COUNT):
            name = f"ppc_recomp.{index}.cpp"
            baseline_path = baseline / name
            source_path = source / name
            output_path = temporary / name
            baseline_parsed = parse_source(baseline_path, mappings)
            source_parsed = parse_source(source_path, mappings)
            require(source_parsed.function_symbols ==
                    baseline_parsed.function_symbols,
                    f"function stream changed in {name}")
            require(source_parsed.markers == baseline_parsed.markers,
                    f"guest-instruction marker stream changed in {name}")
            require(source_parsed.label_count == baseline_parsed.label_count,
                    f"control-flow label count changed in {name}")
            hooks, instrumented_sha = instrument_source(
                source_path, output_path, source_parsed, mappings)
            audited_hooks, file_hook_manifest = audit_instrumented(
                source_path, output_path, source_parsed.markers)
            require(hooks == audited_hooks,
                    f"writer/auditor hook count differs in {name}")
            for marker in source_parsed.markers:
                update_marker_manifest(marker_manifest, name, marker)
                update_marker_manifest(hook_manifest, name, marker)
                unique_addresses.add(marker.address)
            per_file.append({
                "path": name,
                "source_sha256": sha256_file(source_path),
                "instrumented_sha256": instrumented_sha,
                "function_count": len(source_parsed.function_symbols),
                "guest_instruction_occurrence_count":
                    len(source_parsed.markers),
                "hook_count": hooks,
                "control_flow_label_count": source_parsed.label_count,
                "audited_goto_count": source_parsed.goto_count,
                "prologue_count": source_parsed.prologue_count,
                "file_hook_manifest_sha256": file_hook_manifest,
            })
            total_functions += len(source_parsed.function_symbols)
            total_markers += len(source_parsed.markers)
            total_hooks += hooks
            total_labels += source_parsed.label_count
            total_gotos += source_parsed.goto_count

        require(total_functions == EXPECTED_FUNCTION_COUNT,
                f"translated function count changed: {total_functions}")
        require(total_markers == EXPECTED_INSTRUCTION_OCCURRENCES,
                f"instruction occurrence count changed: {total_markers}")
        require(total_hooks == total_markers,
                "global hook/marker count differs")
        require(all(item["function_count"] == item["prologue_count"]
                    for item in per_file),
                "not every translated function has one prologue")
        require(marker_manifest.hexdigest() == hook_manifest.hexdigest(),
                "global marker/hook manifest differs")

        output_roster = exact_roster(temporary)
        output_tree = tree_sha256(temporary, output_roster)
        os.rename(temporary, output)
        renamed = True
    finally:
        if not renamed:
            shutil.rmtree(temporary, ignore_errors=True)

    report = {
        "schema": SCHEMA,
        "result": {
            "source_corpus_read_only": True,
            "source_provenance_stream_exact": True,
            "translated_function_count": total_functions,
            "guest_instruction_occurrence_count": total_markers,
            "unique_guest_instruction_address_count": len(unique_addresses),
            "overlapping_translation_occurrence_count":
                total_markers - len(unique_addresses),
            "instrumented_hook_count": total_hooks,
            "control_flow_label_count": total_labels,
            "audited_goto_count": total_gotos,
            "every_marker_has_exactly_one_immediate_pre_body_hook": True,
            "deinstrumentation_recovers_exact_source": True,
            "uninstrumentable_construct_count": 0,
            "runtime_hook_source_wired_at_every_marker": True,
            "instruction_budget_blocker_resolved_for_derived_corpus": True,
            "entry_call_authorized": False,
            "entry_called": False,
            "translated_title_code_executed_by_pipeline": False,
            "native_boot_proved": False,
        },
        "coverage_proof": {
            "basis": (
                "exact baseline function/marker stream, one injected hook "
                "immediately after every marker, sequential mapping-derived "
                "guest addresses, label-to-next-marker address checks, and "
                "exact source recovery after removing only injected lines"
            ),
            "guest_code_base": f"0x{CODE_BASE:08X}",
            "guest_code_end_exclusive": f"0x{CODE_END_EXCLUSIVE:08X}",
            "minimum_instrumented_address":
                f"0x{min(unique_addresses):08X}",
            "maximum_instrumented_address":
                f"0x{max(unique_addresses):08X}",
            "marker_manifest_sha256": marker_manifest.hexdigest(),
            "hook_manifest_sha256": hook_manifest.hexdigest(),
            "hook_token": HOOK_NAME,
            "hook_position": "immediately after source instruction marker",
            "exhaustion_behavior": (
                "throw typed boundary stop before following translated body"
            ),
        },
        "inputs": {
            "derived_corpus": {
                "path": relative(source, root),
                "tree_sha256": source_tree,
                "file_count": len(source_roster),
            },
            "baseline_corpus": {
                "path": relative(baseline, root),
                "tree_sha256": baseline_tree,
                "file_count": len(baseline_roster),
            },
            "source_manifest": manifest,
            "changed_support_files_bound_by_manifest":
                changed_support_files,
        },
        "output": {
            "instrumented_corpus": relative(output, root),
            "tree_sha256": output_tree,
            "file_count": len(output_roster),
        },
        "files": per_file,
        "scope_boundary": {
            "retail_inputs_modified": False,
            "vendor_tree_modified": False,
            "normal_host_shell_linked": False,
            "title_entry_api_added": False,
            "remaining_semantic_or_boot_blockers_changed_by_this_lane": False,
        },
        "ordered_blockers_for_this_lane": [],
    }
    write_exclusive(report_path,
                    json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        "APF_GUEST_INSTRUCTION_INSTRUMENTATION_PASS "
        f"functions={total_functions} occurrences={total_markers} "
        f"unique_addresses={len(unique_addresses)} hooks={total_hooks} "
        f"labels={total_labels} uninstrumentable=0 "
        "entry_authorized=0 entry_called=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
