#!/usr/bin/env python3
"""Build the isolated APF 2K8 scalar frsqrte semantics audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess


SCHEMA = "apf2k8_frsqrte_semantics/v1"
EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_XENONRECOMP_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
XENIA_COMMIT = "6e5b8324f4101464de0f8c2334edb03cac8826c4"
XENIA_RELEASE_TAG = "6e5b832"
XENIA_SOURCE_SHA256 = {
    "src/xenia/cpu/backend/x64/x64_backend.cc":
        "ab9acc2cc931e72ad55aee2f32fb3a2d693a99c7a698daf3a18a0a9c2525b2e2",
    "src/xenia/cpu/backend/a64/a64_sequences.cc":
        "e4db1101ecc5040185b2a922eb8d8639703c2bc78b3cf507cd9e5ee259828569",
    "src/xenia/cpu/ppc/ppc_emit_fpu.cc":
        "4b7aa5347901f210737d53b8ef3b115aa63d0ad0eebc0795a8cbc8a1240e1ed9",
    "src/xenia/cpu/ppc/ppc_hir_builder.cc":
        "9a7579c3672acb979cfb794af5c0b46be1eaeed2cb6a7325b39962d5933d2b28",
    "src/xenia/cpu/ppc/testing/instr__gen_frsqrte.s":
        "c0bb81fd82e0e2152b5d9bf7bf7f5923dec5fe2a3a563cadc906de514d217fe8",
    "src/xenia/cpu/ppc/testing/instr_frsqrtex.s":
        "5e1a7c7b81957105edd08621e8f7d865fde0d9790566eb7717a50658264417df",
    "src/xenia/cpu/ppc/testing/ppc_testing_native_main.cc":
        "299d7589dcf5784ebd0743ba44cf358b9766591708ad86001801ff5499a67a54",
    "src/xenia/cpu/ppc/testing/ppc_testing_native_thunks.s":
        "0e4130d426d0c108a3063139366f2fe62cd79efd9d5813ee24ef9da7f24bdb67",
}


class SemanticsError(ValueError):
    """Raised when a pinned input or recovered invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SemanticsError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "size": path.stat().st_size, "sha256": sha256(path)}


def hex32(value: int) -> str:
    return f"0x{value:08X}"


FRSP_AND_CORRECTIONS: dict[int, tuple[int, int, int]] = {
    0x84636F00: (0x84636F08, 0x84636F10, 0x84636F1C),
    0x846371C0: (0x846371C8, 0x846371D0, 0x846371DC),
    0x846378A0: (0x846378B4, 0x846378EC, 0x84637928),
    0x846378CC: (0x846378D8, 0x84637910, 0x84637944),
    0x846378E0: (0x84637904, 0x84637924, 0x84637958),
    0x846378F8: (0x8463790C, 0x8463792C, 0x8463795C),
    0x84637A5C: (0x84637A74, 0x84637A7C, 0x84637A88),
    0x84637AAC: (0x84637AC0, 0x84637AC8, 0x84637AD4),
    0x8467BC60: (0x8467BC68, 0x8467BC70, 0x8467BC7C),
    0x847C1E24: (0x847C1E30, 0x847C1E3C, 0x847C1E48),
    0x847EBC7C: (0x847EBC88, 0x847EBC90, 0x847EBC9C),
    0x847F9AC8: (0x847F9AD0, 0x847F9AE4, 0x847F9AF0),
    0x847FB0AC: (0x847FB0B0, 0x847FB0B8, 0x847FB0C4),
    0x8480F1FC: (0x8480F200, 0x8480F208, 0x8480F214),
    0x8480F488: (0x8480F4AC, 0x8480F4B8, 0x8480F4D4),
    0x8480F694: (0x8480F6AC, 0x8480F6B4, 0x8480F6C0),
    0x84841E50: (0x84841E58, 0x84841E60, 0x84841E6C),
    0x848717F0: (0x848717F4, 0x848717FC, 0x84871808),
    0x848782B4: (0x848782BC, 0x848782C4, 0x848782D0),
    0x84878390: (0x84878394, 0x8487839C, 0x848783A8),
    0x848784B4: (0x848784C0, 0x848784C8, 0x848784D4),
    0x84878834: (0x8487883C, 0x84878844, 0x84878850),
    0x848BDCE0: (0x848BDCE8, 0x848BDCF0, 0x848BDCFC),
    0x848C2EE8: (0x848C2EF0, 0x848C2EF8, 0x848C2F04),
    0x848F17D4: (0x848F17D8, 0x848F17E0, 0x848F17EC),
    0x848F7628: (0x848F7630, 0x848F7638, 0x848F7644),
    0x84B12974: (0x84B12978, 0x84B12990, 0x84B1299C),
    0x84B129BC: (0x84B129C0, 0x84B129C8, 0x84B129D8),
}


KNOWN_VECTORS: list[dict[str, object]] = [
    {"input": "0x0000000000000000", "output": "0x7FF0000000000000",
     "class": "+zero", "record_cr": "0x08000000", "fpscr_event": "ZX"},
    {"input": "0x8000000000000000", "output": "0xFFF0000000000000",
     "class": "-zero", "record_cr": "0x08000000", "fpscr_event": "ZX"},
    {"input": "0x0000000000000001", "output": "0x617F100000000000",
     "class": "+subnormal_min", "record_cr": "0x00000000", "fpscr_event": "none"},
    {"input": "0x000FFFFFFFFFFFFF", "output": "0x5FE0800000000000",
     "class": "+subnormal_max", "record_cr": "0x00000000", "fpscr_event": "none"},
    {"input": "0x3FF0000000000000", "output": "0x3FEF100000000000",
     "class": "+normal_one", "record_cr": "0x00000000", "fpscr_event": "none"},
    {"input": "0xBFF0000000000000", "output": "0x7FF8000000000000",
     "class": "-normal", "record_cr": "0x0A000000", "fpscr_event": "VXSQRT"},
    {"input": "0xC1E0000000000000", "output": "0x7FF8000000000000",
     "class": "-normal_large", "record_cr": "0x0A000000", "fpscr_event": "VXSQRT"},
    {"input": "0x41DFFFFFFFC00000", "output": "0x3EF7000000000000",
     "class": "+normal_large", "record_cr": "0x00000000", "fpscr_event": "none"},
    {"input": "0x7FF0000000000000", "output": "0x0000000000000000",
     "class": "+infinity", "record_cr": "0x00000000", "fpscr_event": "none"},
    {"input": "0xFFF0000000000000", "output": "0x7FF8000000000000",
     "class": "-infinity", "record_cr": "0x0A000000", "fpscr_event": "VXSQRT"},
    {"input": "0xFFF8000000000000", "output": "0xFFF8000000000000",
     "class": "quiet_nan", "record_cr": "0x00000000", "fpscr_event": "none"},
    {"input": "0xFFF4000000000000", "output": "0xFFFC000000000000",
     "class": "signaling_nan", "record_cr": "0x0A000000", "fpscr_event": "VXSNAN"},
]


def parse_decoded(path: Path) -> dict[int, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, dialect="excel-tab"))
    result = {
        int(row["address"], 16): row for row in rows if row["mnemonic"] == "frsqrte"
    }
    require(len(result) == 28, "decoded frsqrte address count changed")
    require(set(result) == set(FRSP_AND_CORRECTIONS), "frsqrte address set changed")
    return result


def parse_generated(directory: Path) -> tuple[dict[int, tuple[int, str]], dict[int, list[str]]]:
    files = sorted(directory.glob("ppc_recomp.*.cpp"),
                   key=lambda path: int(path.name.split(".")[1]))
    require(files, "generated XenonRecomp corpus missing")
    instructions: dict[int, tuple[int, str]] = {}
    functions: dict[int, list[str]] = {}
    function_pattern = re.compile(r"PPC_FUNC_IMPL\(__imp__sub_([0-9A-Fa-f]{8})\)")
    for path in files:
        function_start: int | None = None
        address = 0
        body: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            match = function_pattern.match(line)
            if match:
                function_start = int(match.group(1), 16)
                address = function_start
                body = []
                continue
            if function_start is not None and line == "}":
                functions[function_start] = body
                function_start = None
                continue
            if function_start is not None and line.startswith("\t// "):
                text = line[4:]
                if text.startswith("ERROR "):
                    continue
                # The analyzer's deliberately broad function inventory contains a
                # few overlapping false-positive functions. Keep the first linear
                # decode here; every frsqrte/refinement address is asserted below.
                instructions.setdefault(address, (function_start, text))
                body.append(text)
                address += 4
    return instructions, functions


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]),
                                dialect="excel-tab", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xex", type=Path, required=True)
    parser.add_argument("--decoded-tsv", type=Path, required=True)
    parser.add_argument("--generated-dir", type=Path, required=True)
    parser.add_argument("--vendor-root", type=Path, required=True)
    parser.add_argument("--ghidra-powerpc", type=Path, required=True)
    parser.add_argument("--differential-json", type=Path, required=True)
    parser.add_argument("--constants-tsv", type=Path, required=True)
    parser.add_argument("--candidate-patch", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--sites-tsv", type=Path, required=True)
    parser.add_argument("--vectors-tsv", type=Path, required=True)
    args = parser.parse_args()

    require(sha256(args.xex) == EXPECTED_XEX_SHA256, "retail APF XEX changed")
    commit = subprocess.run(
        ["git", "-C", str(args.vendor_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    require(commit == EXPECTED_XENONRECOMP_COMMIT, "XenonRecomp pin changed")

    decoded = parse_decoded(args.decoded_tsv)
    instructions, functions = parse_generated(args.generated_dir)
    containing_functions: set[int] = set()
    site_rows: list[dict[str, object]] = []
    site_records: list[dict[str, object]] = []
    for address in sorted(decoded):
        row = decoded[address]
        require(int(row["raw"], 16) & 1 == 0, f"record form appeared at {hex32(address)}")
        require(instructions[address][1].startswith("frsqrte "),
                f"generated site mismatch at {hex32(address)}")
        function_start = instructions[address][0]
        containing_functions.add(function_start)
        frsp, correction_one, correction_two = FRSP_AND_CORRECTIONS[address]
        require(instructions[frsp][1].startswith("frsp "),
                f"missing frsp at {hex32(frsp)}")
        require(instructions[correction_one][1].startswith("fnmsubs "),
                f"missing first Newton correction at {hex32(correction_one)}")
        require(instructions[correction_two][1].startswith("fnmsubs "),
                f"missing second Newton correction at {hex32(correction_two)}")
        body_mnemonics = {text.split(None, 1)[0] for text in functions[function_start]}
        direct_fpscr_access = bool(body_mnemonics & {
            "mffs", "mcrfs", "mtfsb0", "mtfsb1", "mtfsf", "mtfsfi",
        })
        require(not direct_fpscr_access,
                f"direct FPSCR access appeared in {hex32(function_start)}")
        portme = (
            f"// PORTME({hex32(address)}): use the pinned Xenia 6e5b832 table only "
            "as a value-model candidate; retain FPSCR.NI, FPRF/FR/FI, sticky "
            "exception, and enabled-exception handling until a dense Xenon oracle exists."
        )
        record = {
            "address": hex32(address),
            "raw": row["raw"],
            "operands": row["operands"],
            "function_start": hex32(function_start),
            "record_bit": 0,
            "frsp_address": hex32(frsp),
            "newton_correction_1": hex32(correction_one),
            "newton_correction_2": hex32(correction_two),
            "newton_round_count": 2,
            "direct_fpscr_access_in_containing_function": False,
            "value_status": "pinned_xenia_ieee_model_supported",
            "hardware_arbitrary_input_status": "unproved",
            "portme": portme,
        }
        site_records.append(record)
        site_rows.append(record)

    require(len(containing_functions) == 19, "containing function count changed")
    constants = args.constants_tsv.read_text(encoding="utf-8").splitlines()
    require(constants == [
        "address\traw_be\tfloat32\trole",
        "0x82000A80\t0x3F000000\t0.5\thalf_input",
        "0x82000B18\t0x3FC00000\t1.5\tnewton_three_halves",
    ], "APF Newton constants changed")

    differential = json.loads(args.differential_json.read_text(encoding="utf-8"))
    require(differential["schema"] == "apf2k8_frsqrte_differential/v1",
            "differential schema changed")
    require(differential["known_vector_mismatches"] == 0, "known vector mismatch")
    require(differential["ieee_x64_mismatches"] == 0, "x64 IEEE mismatch")
    require(differential["ieee_a64_mismatches"] == 0, "A64 IEEE mismatch")
    require(differential["non_ieee_x64_a64_divergences"] == 16,
            "Xenia NI divergence evidence changed")
    require(differential["two_round_seed_path_mismatch_count"] == 10986089,
            "refinement result changed")
    require(differential["two_round_seed_path_max_ulp"] == 50,
            "refinement maximum changed")

    recompiler = args.vendor_root / "XenonRecomp/recompiler.cpp"
    context = args.vendor_root / "XenonUtils/ppc_context.h"
    recompiler_text = recompiler.read_text(encoding="utf-8")
    context_text = context.read_text(encoding="utf-8")
    require("case PPC_INST_FRSQRTE:" not in recompiler_text,
            "vendored XenonRecomp now handles frsqrte")
    require("PPC_FRSQRTE_XENIA_6E5B832_VALUE" not in context_text,
            "candidate leaked into vendored context")
    patch_text = args.candidate_patch.read_text(encoding="utf-8")
    require("+    case PPC_INST_FRSQRTE:" in patch_text, "candidate case missing")
    require("PPC_FRSQRTE_XENIA_6E5B832_VALUE" in patch_text,
            "candidate helper missing")
    require("false);" in patch_text, "candidate IEEE-only call boundary changed")
    require(patch_text.count("PORTME") >= 3, "candidate PORTME boundary weakened")

    ghidra_file = args.ghidra_powerpc / "ppc_instructions.sinc"
    ghidra_text = ghidra_file.read_text(encoding="utf-8")
    require(":frsqrte fD,fB" in ghidra_text, "Ghidra frsqrte decode missing")
    require("fD = (floatOne f/ tmpSqrt);" in ghidra_text,
            "Ghidra functional 1/sqrt p-code changed")

    vector_rows = []
    for index, vector in enumerate(KNOWN_VECTORS, start=1):
        vector_rows.append({
            "vector": index,
            **vector,
            "candidate_ieee_match": True,
            "provenance": "xenia_6e5b832_instr__gen_frsqrte",
        })

    xenia_base = f"https://github.com/xenia-canary/xenia-canary/blob/{XENIA_COMMIT}"
    evidence_files = [
        args.xex, args.decoded_tsv, args.differential_json, args.constants_tsv,
        args.candidate_patch, recompiler, context, ghidra_file,
        Path("tools/apf_frsqrte_semantics.py"),
        Path("tools/apf_frsqrte_xex_evidence.cpp"),
        Path("tests/apf_frsqrte_semantics_test.cpp"),
    ]
    report = {
        "schema": SCHEMA,
        "result": {
            "site_count": len(site_records),
            "containing_function_count": len(containing_functions),
            "all_record_bits_zero": True,
            "all_seeds_rounded_to_float32": True,
            "all_sites_have_two_newton_corrections": True,
            "containing_functions_with_direct_fpscr_access": 0,
            "pinned_xenia_ieee_value_model_supported_site_count": 28,
            "architecture_complete_site_count": 0,
            "dense_xenon_hardware_oracle_proved": False,
            "native_runtime_proved": False,
        },
        "powerpc_architecture": {
            "authoritative_source": (
                "https://www.ibm.com/docs/en/aix/7.2.0?topic=set-frsqrte-"
                "floating-reciprocal-square-root-estimate-instruction"
            ),
            "normal_result_contract": "double estimate within one part in 32",
            "estimate_bits_implementation_defined": True,
            "estimate_may_vary_between_executions": True,
            "special_values": {
                "negative_or_negative_infinity": "QNaN and VXSQRT",
                "positive_or_negative_zero": "signed infinity and ZX",
                "positive_infinity": "+0 and no exception",
                "signaling_nan": "quiet NaN and VXSNAN",
                "quiet_nan": "quiet NaN and no exception",
            },
            "enabled_exception_boundary": (
                "VE suppresses the invalid-operation result; ZE suppresses the "
                "zero-divide result"
            ),
            "always_affected_fpscr_fields": [
                "C", "FL", "FG", "FE", "FU", "FR", "FI", "FX", "ZX",
                "VXSNAN", "VXSQRT",
            ],
        },
        "pinned_xenia": {
            "release_tag": XENIA_RELEASE_TAG,
            "commit": XENIA_COMMIT,
            "x64_value_model": (
                "16-entry table; IEEE subnormals normalized; NI subnormals "
                "treated as signed zero"
            ),
            "a64_value_model": (
                "same IEEE table, but the helper does not consult NonIEEE mode"
            ),
            "ieee_source_differential_cases": differential["source_differential_cases"],
            "ieee_x64_mismatches": differential["ieee_x64_mismatches"],
            "ieee_a64_mismatches": differential["ieee_a64_mismatches"],
            "non_ieee_subnormal_cross_backend_cases":
                differential["non_ieee_subnormal_cases"],
            "non_ieee_subnormal_cross_backend_divergences":
                differential["non_ieee_x64_a64_divergences"],
            "checked_in_vector_count": differential["known_vector_count"],
            "checked_in_vector_mismatches": differential["known_vector_mismatches"],
            "vector_provenance": {
                "vector_introduction_commit":
                    "54582cc82349ecaa6411460a94cfdb1d9574d593",
                "vector_commit_subject": "Generated tests from Rick",
                "native_runner_introduction_commit":
                    "ccd6d4b199f1e52612ab4c8b894411f4ae1f46ba",
                "native_runner_fpscr_commit":
                    "6e2bf0b4b129d9b7dac75aeabbe55a16e75b3dea",
                "provenance_strength": (
                    "strong native-PowerPC repository provenance, not a documented "
                    "dense Xenon hardware sweep"
                ),
            },
            "fpscr_implementation_boundary": (
                "PPCHIRBuilder::UpdateFPSCR explicitly leaves overflow/NaN detection "
                "TODO and emits zero new FX/FEX/VX/OX bits; Xenia is a value oracle, "
                "not an FPSCR oracle here"
            ),
            "source_files": [
                {
                    "path": path,
                    "sha256": digest,
                    "url": f"{xenia_base}/{path}",
                }
                for path, digest in XENIA_SOURCE_SHA256.items()
            ],
        },
        "apf_usage": {
            "half_input_constant": {
                "address": "0x82000A80", "raw": "0x3F000000", "value": 0.5,
            },
            "three_halves_constant": {
                "address": "0x82000B18", "raw": "0x3FC00000", "value": 1.5,
            },
            "equation_per_round": "y = y * (1.5f - (0.5f*x*y)*y)",
            "rounding_note": (
                "fmuls rounds the first product; fnmsubs is a fused single-precision "
                "negative multiply-subtract"
            ),
            "refinement_corpus_count": differential["refinement_corpus_count"],
            "raw_maximum_relative_error": differential["maximum_raw_relative_error"],
            "one_round_maximum_relative_error":
                differential["one_round_max_relative_error"],
            "two_round_maximum_relative_error":
                differential["two_round_max_relative_error"],
            "exact_seed_substitution_after_two_rounds": {
                "mismatch_count": differential["two_round_seed_path_mismatch_count"],
                "max_ulp": differential["two_round_seed_path_max_ulp"],
                "finding": (
                    "Newton refinement makes the estimate functionally accurate but "
                    "does not erase seed-dependent bits"
                ),
            },
            "direct_fpscr_access_scope": (
                "No direct mffs/mcrfs/mtfs* instruction occurs inside the 19 containing "
                "functions; this is not an interprocedural call-graph proof"
            ),
        },
        "ghidra_boundary": {
            "decodes_instruction": True,
            "pcode_value_semantics": "functional exact 1/sqrt",
            "estimate_bit_model": False,
            "suitable_as_runtime_oracle": False,
        },
        "candidate_patch": {
            "path": str(args.candidate_patch),
            "applied_to_vendor": False,
            "value_model": "pinned Xenia 6e5b832 table",
            "call_mode": "IEEE hard-coded false for nonIEEE",
            "normal_and_ieee_value_status": "supported against pinned Xenia sources",
            "xenon_arbitrary_input_bit_exact_status": "unproved",
            "fpscr_status": "unimplemented",
            "enabled_exception_status": "unimplemented",
            "ready_to_merge": False,
        },
        "sites": site_records,
        "known_vectors": KNOWN_VECTORS,
        "evidence": {
            "retail_xex_sha256": EXPECTED_XEX_SHA256,
            "xenonrecomp_commit": EXPECTED_XENONRECOMP_COMMIT,
            "files": [pin(path) for path in evidence_files],
        },
        "interpretation": {
            "worked": [
                "Accounted for all 28 scalar frsqrte sites in 19 functions.",
                "Proved every APF site is Rc=0, rounds the seed to float32, and performs two Newton corrections.",
                "Recovered the exact 0.5f and 1.5f constants from the untouched retail XEX.",
                "Matched the candidate IEEE value helper to both pinned Xenia backends over 2,065,536 structured/random cases and all 12 checked-in vectors.",
                "Quantified seed dependence over 16,646,144 positive normal float inputs.",
            ],
            "failed_or_unproved": [
                "The PowerPC architecture intentionally does not define exact estimate bits.",
                "The 12 native-provenance vectors are not a dense arbitrary-input Xenon hardware capture.",
                "Pinned Xenia x64 and A64 disagree for NI-mode subnormal inputs.",
                "Neither Xenia nor XenonRecomp supplies complete FPSCR and enabled-exception behavior here.",
                "No APF runtime execution trace supplied actual inputs at the 28 addresses.",
            ],
            "blocking": [
                "Capture a dense frsqrte input/output/FPSCR matrix on Xenon hardware or a trusted hardware oracle.",
                "Track guest FPSCR.NI and status fields in the static-recomp runtime.",
                "Implement VE/ZE no-result behavior before calling the instruction architecture-complete.",
            ],
        },
    }

    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_tsv(args.sites_tsv, site_rows)
    write_tsv(args.vectors_tsv, vector_rows)
    print(
        "APF_FRSQRTE_SEMANTICS_COMPLETE "
        f"sites={len(site_records)} functions={len(containing_functions)} "
        "xenia_vectors=12 hardware_dense=no fpscr=no"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
