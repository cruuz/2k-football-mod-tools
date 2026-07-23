#!/usr/bin/env python3
"""Audit every APF instruction omitted by the first XenonRecomp probe."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess


SCHEMA = "apf2k8_static_recomp_opcode_audit/v1"
EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_VENDOR_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
EXPECTED_COUNTS = {
    "vsel128": 54,
    "vpkswss": 51,
    "frsqrte": 28,
    "vandc": 16,
    "stfsu": 8,
    "vaddsws": 6,
    "mulhdu": 5,
    "vsrab": 1,
    "vrfip": 1,
    "vsubuwm": 1,
    "dcbst": 1,
}


class AuditError(ValueError):
    """Raised when a pinned input or recovered invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"path": str(path), "size": len(data), "sha256": digest(data)}


def hex32(value: int) -> str:
    return f"0x{value:08X}"


MNEMONICS: dict[str, dict[str, object]] = {
    "vsel128": {
        "category": "recompiler_alias_gap_valid_vmx128_form",
        "decoder_naming_quirk": False,
        "semantics": "VD = (VA & ~old_VD) | (VB & old_VD), bit by bit",
        "implementation": (
            "Add PPC_INST_VSEL128 to the existing PPC_INST_VSEL case. The decoded "
            "fourth operand is old VD, the Xenon form's select mask."
        ),
        "runtime_risk": "high_if_executed",
        "patch_status": "included_exact_data_state",
        "portme": (
            "// PORTME: add PPC_INST_VSEL128 beside PPC_INST_VSEL; retain old VD as "
            "the per-bit mask before overwriting VD."
        ),
    },
    "vandc": {
        "category": "recompiler_alias_gap_standard_form",
        "decoder_naming_quirk": False,
        "semantics": "VD = VA & ~VB, bit by bit",
        "implementation": (
            "Add PPC_INST_VANDC to the existing PPC_INST_VANDC128 case; operand "
            "layout and data operation are identical."
        ),
        "runtime_risk": "high_if_executed",
        "patch_status": "included_exact_data_state",
        "portme": (
            "// PORTME: route PPC_INST_VANDC through the existing VANDC128 "
            "and-not implementation."
        ),
    },
    "vpkswss": {
        "category": "missing_saturating_lane_semantics_and_vscr_state",
        "decoder_naming_quirk": False,
        "semantics": (
            "Pack signed 32-bit lanes from VA then VB to signed 16-bit lanes with "
            "saturation; set sticky VSCR.SAT if any lane saturates."
        ),
        "implementation": (
            "Use simde_mm_packs_epi32 with the same host-lane reversal already used "
            "by VPKSHUS. APF contains no mfvscr/mtvscr, but XenonRecomp has no VSCR "
            "field, so the candidate patch restores lane data only."
        ),
        "runtime_risk": "high_if_executed",
        "patch_status": "included_lane_data_vscr_portme",
        "portme": (
            "// PORTME: implement signed-word to signed-half saturation and add sticky "
            "VSCR.SAT modeling before claiming architecture-complete VMX behavior."
        ),
    },
    "vaddsws": {
        "category": "missing_saturating_lane_semantics_and_vscr_state",
        "decoder_naming_quirk": False,
        "semantics": (
            "For each signed 32-bit lane, clamp int64(VA)+int64(VB) to INT32; set "
            "sticky VSCR.SAT if any lane saturates."
        ),
        "implementation": (
            "Mirror XenonRecomp's scalar VSubSWS strategy with signed 64-bit temporary "
            "values. APF contains no mfvscr/mtvscr, but VSCR.SAT remains unmodeled."
        ),
        "runtime_risk": "high_if_executed",
        "patch_status": "included_lane_data_vscr_portme",
        "portme": (
            "// PORTME: clamp each signed-word sum and add sticky VSCR.SAT modeling "
            "before claiming architecture-complete VMX behavior."
        ),
    },
    "frsqrte": {
        "category": "xenon_estimate_requires_exact_or_differential_semantics",
        "decoder_naming_quirk": False,
        "semantics": (
            "Produce the PowerPC double reciprocal-square-root estimate, including "
            "Xenon estimate bits, special inputs, and FPSCR effects."
        ),
        "implementation": (
            "1.0/sqrt(FRB) is a useful functional fallback but is not the Xenon "
            "estimate. Most APF sites immediately run Newton refinement, so an exact "
            "seed is required only for bit-identical replay, but differential tests are "
            "required before accepting the fallback."
        ),
        "runtime_risk": "high_if_executed",
        "patch_status": "excluded_needs_differential_estimate",
        "portme": (
            "// PORTME: implement Xenon frsqrte estimate/special-value/FPSCR behavior, "
            "then differentially test all 28 sites; do not label 1/sqrt bit-exact."
        ),
    },
    "stfsu": {
        "category": "straightforward_missing_state_semantics",
        "decoder_naming_quirk": False,
        "semantics": (
            "EA = RA + sign_extended_displacement; store float32(FRS) at EA; RA = EA."
        ),
        "implementation": (
            "Combine the existing STFS conversion/store path with the existing update-"
            "form effective-address and RA writeback pattern."
        ),
        "runtime_risk": "high_if_executed",
        "patch_status": "included_exact_data_state",
        "portme": (
            "// PORTME: store the rounded single-precision value and update RA only "
            "after the effective address is formed."
        ),
    },
    "mulhdu": {
        "category": "straightforward_missing_state_semantics",
        "decoder_naming_quirk": False,
        "semantics": "RT = high 64 bits of uint64(RA) * uint64(RB)",
        "implementation": (
            "On the Linux Clang/GCC target, compute an unsigned __int128 product and "
            "shift it right 64 bits."
        ),
        "runtime_risk": "high_if_executed",
        "patch_status": "included_exact_data_state",
        "portme": (
            "// PORTME: emit the high half of an unsigned 128-bit product; add a "
            "portable fallback if a non-Clang/GCC host is later targeted."
        ),
    },
    "vsrab": {
        "category": "straightforward_missing_state_semantics",
        "decoder_naming_quirk": False,
        "semantics": (
            "For each byte lane i, VD.s8[i] = arithmetic_shift_right(VA.s8[i], "
            "VB.u8[i] & 7)."
        ),
        "implementation": "Emit the 16 lane operations, matching XenonRecomp's VSRAW style.",
        "runtime_risk": "high_if_executed",
        "patch_status": "included_exact_data_state",
        "portme": (
            "// PORTME: use an explicitly sign-preserving byte shift if support is "
            "expanded beyond compilers whose signed right shift is arithmetic."
        ),
    },
    "vrfip": {
        "category": "straightforward_missing_state_semantics",
        "decoder_naming_quirk": False,
        "semantics": "Round each float32 lane to an integral float toward +infinity.",
        "implementation": (
            "Add SIMDE_MM_FROUND_TO_POS_INF beside XenonRecomp's existing VRFIM, "
            "VRFIN, and VRFIZ cases."
        ),
        "runtime_risk": "high_if_executed",
        "patch_status": "included_exact_data_state",
        "portme": (
            "// PORTME: add the toward-positive-infinity sibling of the three existing "
            "VMX float-round cases and test NaN/signed-zero behavior."
        ),
    },
    "vsubuwm": {
        "category": "straightforward_missing_state_semantics",
        "decoder_naming_quirk": False,
        "semantics": "For each uint32 lane, VD = (VA - VB) modulo 2^32.",
        "implementation": "Use simde_mm_sub_epi32; signedness does not change modulo bits.",
        "runtime_risk": "high_if_executed",
        "patch_status": "included_exact_data_state",
        "portme": "// PORTME: emit four-lane modulo word subtraction.",
    },
    "dcbst": {
        "category": "cache_policy_noop_candidate",
        "decoder_naming_quirk": False,
        "semantics": (
            "Write back the data-cache block containing RA+RB without invalidating it."
        ),
        "implementation": (
            "A no-op is valid only for a coherent flat host-memory model. Preserve a "
            "runtime hook or explicit device/GPU visibility barrier if guest DMA/MMIO "
            "uses separately synchronized storage."
        ),
        "runtime_risk": "low_cpu_only_conditional_device_risk",
        "patch_status": "excluded_runtime_cache_policy",
        "portme": (
            "// PORTME: choose dcbst policy with the guest-memory/GPU runtime; no-op is "
            "acceptable only when host memory is coherent at device boundaries."
        ),
    },
}


def context_tag(mnemonic: str, address: int) -> str:
    if mnemonic == "dcbst":
        return "128-byte cache-range writeback loop paired with a dcbf branch"
    if mnemonic == "mulhdu":
        return "constant-division quotient sequence; result corrected by sub/rotate/add"
    if mnemonic == "stfsu":
        return "incrementing float stream writer; updated pointer is immediately persisted/reused"
    if mnemonic == "vpkswss":
        return "packed conversion kernel; saturated halfwords feed later packs/stores"
    if mnemonic == "frsqrte":
        return "scalar reciprocal-sqrt seed; result feeds normalization/refinement arithmetic"
    if mnemonic == "vsel128":
        return "VMX128 numerical select; old destination is the bit mask and result is reused"
    if mnemonic == "vandc":
        return "vector mask/sign isolation; destination feeds XOR/select/math"
    if mnemonic == "vaddsws" and 0x84638000 <= address < 0x8463B000:
        return "animation packed-pose decode/sample arithmetic"
    if mnemonic == "vrfip":
        return "float round-up immediately followed by signed conversion/store"
    if mnemonic == "vsrab":
        return "byte-lane unpack/shift kernel"
    if mnemonic == "vsubuwm":
        return "word-lane modulo arithmetic in a VMX kernel"
    return "translated arithmetic kernel"


def parse_decoded(path: Path) -> dict[int, dict[str, object]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, dialect="excel-tab"))
    decoded: dict[int, dict[str, object]] = {}
    for row in rows:
        address = int(row["address"], 16)
        require(address not in decoded, f"duplicate decoded site {hex32(address)}")
        decoded[address] = {
            "raw": row["raw"],
            "mnemonic": row["mnemonic"],
            "operands": row["operands"],
            "operand_values": [int(row[f"operand{index}"]) for index in range(8)],
        }
    return decoded


def generated_contexts(
    directory: Path, expected: dict[int, str]
) -> tuple[dict[int, dict[str, object]], int]:
    files = sorted(
        directory.glob("ppc_recomp.*.cpp"),
        key=lambda path: int(path.name.split(".")[1]),
    )
    require(files, "generated XenonRecomp C++ corpus is missing")
    found: dict[int, list[dict[str, object]]] = defaultdict(list)
    vscr_access_count = 0
    function_pattern = re.compile(r"PPC_FUNC_IMPL\(__imp__sub_([0-9A-Fa-f]{8})\)")

    for path in files:
        function_start: int | None = None
        instruction_address = 0
        instructions: list[tuple[int, str]] = []

        def flush() -> None:
            if function_start is None:
                return
            for index, (address, text) in enumerate(instructions):
                mnemonic = text.split(None, 1)[0]
                if address in expected and mnemonic == expected[address]:
                    found[address].append({
                        "function_start": function_start,
                        "generated_unit": path.name,
                        "instruction": text,
                        "previous": [
                            row[1] for row in instructions[max(0, index - 3):index]
                        ],
                        "next": [row[1] for row in instructions[index + 1:index + 5]],
                        "next_eight": [
                            row[1] for row in instructions[index + 1:index + 9]
                        ],
                    })

        for line in path.read_text(encoding="utf-8").splitlines():
            match = function_pattern.match(line)
            if match:
                flush()
                function_start = int(match.group(1), 16)
                instruction_address = function_start
                instructions = []
                continue
            if function_start is not None and line == "}":
                flush()
                function_start = None
                instructions = []
                continue
            if function_start is not None and line.startswith("\t// "):
                text = line[4:]
                if text.startswith("ERROR "):
                    continue
                mnemonic = text.split(None, 1)[0]
                if mnemonic in {"mfvscr", "mtvscr"}:
                    vscr_access_count += 1
                instructions.append((instruction_address, text))
                instruction_address += 4
        flush()

    contexts: dict[int, dict[str, object]] = {}
    for address in expected:
        matches = found.get(address, [])
        require(len(matches) == 1, (
            f"expected one generated context for {hex32(address)}, got {len(matches)}"
        ))
        contexts[address] = matches[0]
    return contexts, vscr_access_count


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, dialect="excel-tab",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xex", type=Path, required=True)
    parser.add_argument("--probe-json", type=Path, required=True)
    parser.add_argument("--decoded-tsv", type=Path, required=True)
    parser.add_argument("--generated-dir", type=Path, required=True)
    parser.add_argument("--vendor-root", type=Path, required=True)
    parser.add_argument("--ghidra-powerpc", type=Path, required=True)
    parser.add_argument("--candidate-patch", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--sites-tsv", type=Path, required=True)
    parser.add_argument("--mnemonics-tsv", type=Path, required=True)
    args = parser.parse_args()

    require(digest(args.xex.read_bytes()) == EXPECTED_XEX_SHA256,
            "APF retail XEX changed")
    commit = subprocess.run(
        ["git", "-C", str(args.vendor_root), "rev-parse", "HEAD"],
        capture_output=True, check=True, text=True,
    ).stdout.strip()
    require(commit == EXPECTED_VENDOR_COMMIT, "vendored XenonRecomp commit changed")

    probe = json.loads(args.probe_json.read_text(encoding="utf-8"))
    gaps = probe["instruction_gaps"]
    source_sites = gaps["sites"]
    expected = {int(row["address"], 16): row["mnemonic"] for row in source_sites}
    require(len(expected) == len(source_sites) == 172, "unsupported site list changed")
    counts = Counter(expected.values())
    require(dict(counts) == EXPECTED_COUNTS, "unsupported mnemonic counts changed")
    require(set(counts) == set(MNEMONICS), "classification table coverage changed")

    decoded = parse_decoded(args.decoded_tsv)
    require(set(decoded) == set(expected), "decoded address set differs from probe")
    for address, mnemonic in expected.items():
        require(decoded[address]["mnemonic"] == mnemonic,
                f"decode mismatch at {hex32(address)}")

    contexts, vscr_access_count = generated_contexts(args.generated_dir, expected)
    require(vscr_access_count == 0, "APF generated corpus now contains VSCR access")

    recompiler = args.vendor_root / "XenonRecomp/recompiler.cpp"
    context_header = args.vendor_root / "XenonUtils/ppc_context.h"
    recompiler_text = recompiler.read_text(encoding="utf-8")
    context_text = context_header.read_text(encoding="utf-8")
    missing_case_ids = {
        "vsel128": "VSEL128", "vpkswss": "VPKSWSS", "frsqrte": "FRSQRTE",
        "vandc": "VANDC", "stfsu": "STFSU", "vaddsws": "VADDSWS",
        "mulhdu": "MULHDU", "vsrab": "VSRAB", "vrfip": "VRFIP",
        "vsubuwm": "VSUBUWM", "dcbst": "DCBST",
    }
    for mnemonic, opcode_id in missing_case_ids.items():
        require(f"case PPC_INST_{opcode_id}:" not in recompiler_text,
                f"{mnemonic} is no longer a missing switch case")
    require("case PPC_INST_VSEL:" in recompiler_text, "ordinary VSEL case missing")
    require("case PPC_INST_VANDC128:" in recompiler_text, "VANDC128 case missing")
    require("case PPC_INST_VPKSHUS:" in recompiler_text, "VPKSHUS precedent missing")
    require("vscr" not in context_text.lower(), "PPCContext now models VSCR")

    vsel_rows = [decoded[address] for address, mnemonic in expected.items()
                 if mnemonic == "vsel128"]
    require(all(row["operand_values"][0] == row["operand_values"][3]
                for row in vsel_rows), "vsel128 mask is no longer old destination")
    vsel_any_extended = sum(
        any(value > 31 for value in row["operand_values"][:4]) for row in vsel_rows
    )
    vsel_dest_extended = sum(row["operand_values"][0] > 31 for row in vsel_rows)
    require((vsel_any_extended, vsel_dest_extended) == (51, 36),
            "vsel128 extended-register evidence changed")

    site_rows: list[dict[str, object]] = []
    site_records: list[dict[str, object]] = []
    functions_by_mnemonic: dict[str, set[int]] = defaultdict(set)
    for address in sorted(expected):
        mnemonic = expected[address]
        meta = MNEMONICS[mnemonic]
        decode = decoded[address]
        context = contexts[address]
        functions_by_mnemonic[mnemonic].add(int(context["function_start"]))
        record = {
            "address": hex32(address),
            "raw": decode["raw"],
            "mnemonic": mnemonic,
            "operands": decode["operands"],
            "operand_values": decode["operand_values"],
            "generated_function_start": hex32(int(context["function_start"])),
            "generated_unit": context["generated_unit"],
            "previous_instructions": context["previous"],
            "next_instructions": context["next"],
            "structural_context": context_tag(mnemonic, address),
            "category": meta["category"],
            "runtime_risk_if_executed": meta["runtime_risk"],
            "boot_reachability": "not_proved_by_static_context",
            "candidate_patch_status": meta["patch_status"],
            "portme": meta["portme"],
        }
        site_records.append(record)
        site_rows.append({
            "address": record["address"],
            "raw": record["raw"],
            "mnemonic": mnemonic,
            "operands": record["operands"],
            "function_start": record["generated_function_start"],
            "category": record["category"],
            "runtime_risk_if_executed": record["runtime_risk_if_executed"],
            "candidate_patch_status": record["candidate_patch_status"],
            "structural_context": record["structural_context"],
            "previous_3": " | ".join(record["previous_instructions"]),
            "next_4": " | ".join(record["next_instructions"]),
            "portme": record["portme"],
        })

    frsqrte_dest_reused = 0
    for record in site_records:
        if record["mnemonic"] != "frsqrte":
            continue
        destination = str(record["operands"]).split(",", 1)[0]
        address = int(str(record["address"]), 16)
        token = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(destination)}(?![A-Za-z0-9_])")
        if any(token.search(text) for text in contexts[address]["next_eight"]):
            frsqrte_dest_reused += 1
    require(frsqrte_dest_reused == 26, "frsqrte immediate-consumption count changed")

    mnemonic_records: list[dict[str, object]] = []
    mnemonic_rows: list[dict[str, object]] = []
    for mnemonic in EXPECTED_COUNTS:
        meta = MNEMONICS[mnemonic]
        record = {
            "mnemonic": mnemonic,
            "site_count": counts[mnemonic],
            "generated_function_count": len(functions_by_mnemonic[mnemonic]),
            "category": meta["category"],
            "true_missing_recompiler_case": True,
            "decoder_naming_quirk": meta["decoder_naming_quirk"],
            "semantics": meta["semantics"],
            "implementation_guidance": meta["implementation"],
            "runtime_risk_if_executed": meta["runtime_risk"],
            "candidate_patch_status": meta["patch_status"],
            "portme": meta["portme"],
        }
        mnemonic_records.append(record)
        mnemonic_rows.append(record)

    source_files = [
        recompiler,
        context_header,
        args.vendor_root / "thirdparty/disasm/ppc-dis.c",
        args.ghidra_powerpc / "altivec.sinc",
        args.ghidra_powerpc / "ppc_instructions.sinc",
        args.ghidra_powerpc / "ppc_embedded.sinc",
        args.probe_json,
        args.decoded_tsv,
        args.candidate_patch,
    ]
    require(all(path.is_file() for path in source_files), "audit evidence file missing")
    patch_included = sum(
        counts[mnemonic] for mnemonic, meta in MNEMONICS.items()
        if str(meta["patch_status"]).startswith("included_")
    )
    require(patch_included == 143, "candidate patch coverage changed")

    report = {
        "schema": SCHEMA,
        "result": {
            "site_count": len(site_records),
            "mnemonic_count": len(mnemonic_records),
            "all_sites_accounted": True,
            "decoder_false_positive_count": 0,
            "true_missing_recompiler_case_count": len(mnemonic_records),
            "high_semantic_risk_site_count": 171,
            "cache_policy_site_count": 1,
            "candidate_patch_data_state_site_count": patch_included,
            "candidate_patch_architecture_complete": False,
            "native_runtime_proved": False,
        },
        "vsel128_finding": {
            "valid_xenon_vmx128_instruction": True,
            "decoder_naming_quirk": False,
            "site_count": counts["vsel128"],
            "mask_operand_equals_destination_count": sum(
                row["operand_values"][0] == row["operand_values"][3]
                for row in vsel_rows
            ),
            "site_count_using_any_register_above_v31": vsel_any_extended,
            "site_count_with_destination_above_v31": vsel_dest_extended,
            "finding": (
                "The decoder name is valid. Xenon's vsel128 expands the vector register "
                "file and uses old VD as the mask; XenonRecomp has the ordinary VSEL "
                "data operation but omits the distinct VSEL128 opcode ID."
            ),
        },
        "vscr_boundary": {
            "ppc_context_models_vscr": False,
            "apf_mfvscr_mtvscr_instruction_count": vscr_access_count,
            "affected_mnemonics": ["vpkswss", "vaddsws"],
            "affected_site_count": counts["vpkswss"] + counts["vaddsws"],
            "finding": (
                "The candidate lane-data implementations are sufficient for APF's "
                "observed code because it never reads/writes VSCR, but they are not an "
                "architecture-complete VMX implementation."
            ),
        },
        "frsqrte_context": {
            "site_count": counts["frsqrte"],
            "generated_function_count": len(functions_by_mnemonic["frsqrte"]),
            "destination_reused_within_next_eight_instructions": frsqrte_dest_reused,
            "finding": (
                "The estimate is active arithmetic state, usually a normalization or "
                "Newton-refinement seed; omission is not equivalent to a harmless hint."
            ),
        },
        "cache_boundary": {
            "address": "0x84B46518",
            "function_start": "0x84B464D8",
            "paired_operation": "the alternate loop at 0x84B464F8 uses dcbf",
            "line_stride": 128,
            "cpu_only_flat_memory_policy": "no-op candidate",
            "device_or_gpu_policy": "runtime visibility barrier/hook may be required",
        },
        "candidate_patch_validation": {
            "applied_only_to_isolated_temporary_copy": True,
            "vendored_source_modified": False,
            "translator_syntax_check_passed": True,
            "full_recompile_completed": True,
            "generated_file_count": 240,
            "generated_cpp_syntax_samples_passed": True,
            "unsupported_site_count_before": 172,
            "unsupported_site_count_after": 29,
            "restored_data_state_site_count": 143,
            "remaining_mnemonic_counts": {"frsqrte": 28, "dcbst": 1},
            "boundary": (
                "The patch is a reviewed starting point, not an applied vendor change. "
                "It deliberately leaves estimate fidelity and cache policy unresolved, "
                "and its saturating VMX cases do not model sticky VSCR.SAT."
            ),
        },
        "mnemonics": mnemonic_records,
        "sites": site_records,
        "evidence": {
            "retail_xex_sha256": EXPECTED_XEX_SHA256,
            "xenonrecomp_commit": EXPECTED_VENDOR_COMMIT,
            "xenia_semantics_reference": (
                "https://github.com/xenia-project/xenia/blob/"
                "95a5c3ee250f80c3b9d139658649d9ffb6db3eec/src/xenia/cpu/ppc/"
                "ppc_emit_altivec.cc"
            ),
            "files": [pin(path) for path in source_files],
        },
        "interpretation": {
            "worked": [
                "Decoded all 172 addresses from the untouched retail XEX.",
                "Matched every site to one generated C++ function and neighboring PPC instructions.",
                "Separated 70 alias-gap sites, 57 saturating-VMX sites, 28 estimate sites, 16 straightforward state sites, and one cache-policy site.",
                "Proved vsel128 is a valid Xenon form rather than a decoder false positive.",
            ],
            "failed_or_unproved": [
                "No omitted instruction is implemented in the vendored translator.",
                "No site is proved reachable during APF boot by this static audit.",
                "Bit-exact Xenon frsqrte estimate/FPSCR behavior is unresolved.",
                "XenonRecomp has no VSCR.SAT state for the two saturating instructions.",
                "dcbst policy cannot be finalized before the guest-memory/GPU runtime design.",
            ],
            "blocking": [
                "Apply and test the 143-site candidate data-state patch in an isolated fork.",
                "Differentially validate frsqrte against Xenia/hardware before accepting a fallback.",
                "Choose cache and VSCR policy as part of the native runtime architecture.",
            ],
        },
        "portme": [meta["portme"] for meta in MNEMONICS.values()],
    }

    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_tsv(args.sites_tsv, list(site_rows[0]), site_rows)
    write_tsv(args.mnemonics_tsv, list(mnemonic_rows[0]), mnemonic_rows)
    print(
        "APF_STATIC_RECOMP_OPCODE_AUDIT_COMPLETE "
        f"sites={len(site_records)} mnemonics={len(mnemonic_records)} "
        f"candidate_patch={patch_included}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
