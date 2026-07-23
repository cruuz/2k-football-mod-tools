#!/usr/bin/env python3
"""Build APF's source-pinned dcbst semantic and candidate-hook report.

The candidate remains unapplied.  A validator supplies a deterministic
observation produced by rebuilding the translator in a temporary copy,
regenerating APF, syntax-checking every generated translation unit, and
running the host-only hook contract test.  No translated title code is run.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


SCHEMA = "apf2k8_dcbst_semantics/v1"
OBSERVATION_SCHEMA = "apf2k8_dcbst_candidate_observation/v1"
IBM_DCBST_URL = (
    "https://www.ibm.com/docs/en/aix/7.2.0?topic=set-dcbst-"
    "data-cache-block-store-instruction"
)

EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_VENDOR_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
EXPECTED_XENIA_COMMIT = "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"
EXPECTED_RECOMPILER_SHA256 = (
    "30e7ea5b4d8a225bc3e0ac71aebd1a0af7bcde5aaf5679517719b559c9cd777a"
)
EXPECTED_CONTEXT_SHA256 = (
    "369acaf639c52bb25ee8a2c6a555c7875912f0692b1e8220ea8dab0384e42263"
)
EXPECTED_DECODED_TSV_SHA256 = (
    "0477095b2e59cad46f76002fabdb3b4db3e6c016721cc49992510e1e1a02d33f"
)
EXPECTED_BASELINE_UNIT_SHA256 = (
    "93a7ca8327335453386eed4dcdb8f0bb47d33e30fa170b64335bbed5f8a63d98"
)
EXPECTED_PATCH_SHA256 = (
    "018ce6f0fe2596b59606cfd85eb77648eaa32fcecab7ff78a213ac2128847de1"
)
EXPECTED_HOOK_TEST_SHA256 = (
    "21155e45fe713f0e6a25f538dfce206891f4c17a3505054c50004d7791b15b26"
)

XENIA_SOURCE_HASHES = {
    "src/xenia/cpu/ppc/ppc_emit_memory.cc":
        "e9682009fdf0d0484d2bff3401287801df2ed5977c966c7c81371968e32082c7",
    "src/xenia/cpu/backend/x64/x64_seq_memory.cc":
        "e8a48c66dcbe7ab46bc6e1f2b63942de2b5fdf65c5b1ea75e62598ac9232afae",
    "src/xenia/cpu/hir/opcodes.h":
        "9399dc0456c37bd4a5cde7986309d736167f69c9e93a287dfcc819b44c0b4060",
    "src/xenia/cpu/hir/hir_builder.cc":
        "dc4baae76e69ca85d56839494743297797a0226c578dd1d5266d8930c456c595",
}

SITE_ADDRESS = 0x84B46518
FUNCTION_ADDRESS = 0x84B464D8
DCBF_ADDRESS = 0x84B464F8
RAW_WORD = 0x7C0B486C
RA = 11
RB = 9
XENON_LINE_SIZE = 128

EXPECTED_AFTER_COUNTS = {
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

EXPECTED_HOOK_STDOUT = (
    "APF_DCBST_HOOK_TEST_PASS nonzero_ra_ea=0x00000145 "
    "nonzero_ra_line=0x00000100 rb_only_ea=0x00ABCDEF "
    "rb_only_line=0x00ABCD80 line_size=128 default_signal=6 "
    "invalid_size_signal=6\n"
)
EXPECTED_SITE_PORTME = (
    "// PORTME(0x84B46518): enforce load-like guest protection and "
    "GPU/DMA/MMIO visibility; install a proved coherent-flat-RAM no-op "
    "only when every consumer shares storage."
)


class DcbstError(RuntimeError):
    """Raised when pinned semantic evidence changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DcbstError(message)


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def pin(path: Path, expected: str | None = None) -> dict[str, object]:
    digest = sha256_file(path)
    if expected is not None:
        require(digest == expected, f"pinned file changed: {path}")
    return {"path": str(path), "size": path.stat().st_size, "sha256": digest}


def line_of(text: str, needle: str) -> int:
    require(needle in text, f"source statement missing: {needle}")
    return text[:text.index(needle)].count("\n") + 1


def git_head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    require(completed.returncode == 0, f"not a git tree: {path}")
    return completed.stdout.strip()


def require_tracked_clean(path: Path) -> None:
    for args in (("diff", "--quiet", "HEAD", "--"),
                 ("diff", "--cached", "--quiet", "HEAD", "--")):
        completed = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True, text=True, check=False,
        )
        require(completed.returncode == 0,
                f"tracked source changes present: {path}")


def parse_site(decoded_path: Path) -> dict[str, object]:
    pin(decoded_path, EXPECTED_DECODED_TSV_SHA256)
    with decoded_path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, dialect="excel-tab"))
    sites = [row for row in rows if row["mnemonic"] == "dcbst"]
    require(len(sites) == 1, "dcbst site count changed")
    row = sites[0]
    require(row["address"] == "0x84B46518", "dcbst address changed")
    require(row["raw"] == "0x7C0B486C", "dcbst raw word changed")
    require(row["operands"] == "r11,r9", "dcbst operands changed")

    raw = int(row["raw"], 16)
    decoded = {
        "primary_opcode": raw >> 26,
        "ra": (raw >> 16) & 31,
        "rb": (raw >> 11) & 31,
        "extended_opcode": (raw >> 1) & 0x3FF,
        "record_bit": raw & 1,
    }
    require(decoded == {
        "primary_opcode": 31,
        "ra": RA,
        "rb": RB,
        "extended_opcode": 54,
        "record_bit": 0,
    }, "dcbst X-form decode changed")
    return {
        "address": "0x84B46518",
        "raw_word": "0x7C0B486C",
        "operands": "r11,r9",
        "ra": RA,
        "rb": RB,
        "x_form_decode": decoded,
    }


def inspect_baseline(unit_path: Path) -> dict[str, object]:
    pin(unit_path, EXPECTED_BASELINE_UNIT_SHA256)
    text = unit_path.read_text(encoding="utf-8")
    expected_fragments = [
        "PPC_FUNC_IMPL(__imp__sub_84B464D8)",
        "// clrlwi r11,r3,25",
        "// subf r9,r11,r3",
        "loc_84B464F8:",
        "// dcbf r11,r9",
        "loc_84B46518:",
        "// dcbst r11,r9",
        "// addi r11,r11,128",
        "if (ctx.cr6.lt) goto loc_84B46518;",
    ]
    for fragment in expected_fragments:
        require(fragment in text, f"APF cache loop changed: {fragment}")
    require(text.count("// dcbst r11,r9") == 1,
            "baseline dcbst comment count changed")
    require("PPC_DATA_CACHE_BLOCK_STORE" not in text,
            "baseline unexpectedly contains candidate hook")
    return {
        "generated_unit": unit_path.name,
        "function_start": "0x84B464D8",
        "dcbst_address": "0x84B46518",
        "alternate_dcbf_address": "0x84B464F8",
        "loop_stride_bytes": 128,
        "range_start_computation": "r9 = r3 - (r3 & 0x7F)",
        "dcbst_effective_address": "uint32(r11 + r9)",
        "baseline_dcbst_emission": "comment_only",
        "baseline_dcbf_emission": "recognized_but_no_op",
    }


def inspect_xenia(xenia: Path) -> dict[str, object]:
    require(git_head(xenia) == EXPECTED_XENIA_COMMIT,
            "pinned Xenia commit changed")
    require_tracked_clean(xenia)
    pins = {}
    for relative, expected in XENIA_SOURCE_HASHES.items():
        pins[relative] = pin(xenia / relative, expected)

    emit_path = xenia / "src/xenia/cpu/ppc/ppc_emit_memory.cc"
    x64_path = xenia / "src/xenia/cpu/backend/x64/x64_seq_memory.cc"
    hir_path = xenia / "src/xenia/cpu/hir/hir_builder.cc"
    emit = emit_path.read_text(encoding="utf-8")
    x64 = x64_path.read_text(encoding="utf-8")
    hir = hir_path.read_text(encoding="utf-8")
    ea_needle = "Value* CalculateEA_0(PPCHIRBuilder& f, uint32_t ra, uint32_t rb)"
    dcbst_needle = "int InstrEmit_dcbst(PPCHIRBuilder& f, const InstrData& i)"
    control_needle = (
        "f.CacheControl(ea, 128, CacheControlType::CACHE_CONTROL_TYPE_DATA_STORE);"
    )
    require(ea_needle in emit and "if (ra) {" in emit and
            "return f.LoadGPR(rb);" in emit,
            "Xenia RA0 EA calculation changed")
    require(dcbst_needle in emit and control_needle in emit,
            "Xenia dcbst CacheControl emission changed")
    require("CACHE_CONTROL_TYPE_DATA_STORE:" in x64 and
            "is_clflush = true;" in x64 and
            "e.clflush(e.ptr[addr]);" in x64 and
            "e.xor_(e.eax, 64);" in x64 and
            "assert_true(cache_line_size == 128);" in x64,
            "Xenia x64 cache-control lowering changed")
    require("void HIRBuilder::CacheControl" in hir and
            "i->src2.offset = cache_line_size;" in hir,
            "Xenia HIR CacheControl contract changed")
    return {
        "commit": EXPECTED_XENIA_COMMIT,
        "effective_address_helper": {
            "path": "src/xenia/cpu/ppc/ppc_emit_memory.cc",
            "line": line_of(emit, ea_needle),
            "contract": "RA != 0 ? GPR[RA] + GPR[RB] : GPR[RB]",
        },
        "dcbst_emitter": {
            "path": "src/xenia/cpu/ppc/ppc_emit_memory.cc",
            "line": line_of(emit, dcbst_needle),
            "cache_control_type": "DATA_STORE",
            "xenon_cache_line_size": 128,
        },
        "x64_lowering": {
            "path": "src/xenia/cpu/backend/x64/x64_seq_memory.cc",
            "line": line_of(x64, "struct CACHE_CONTROL"),
            "data_store_action": "clflush addressed host line",
            "second_half_action": "xor address bit 6 and clflush",
            "modeled_xenon_line_bytes": 128,
        },
        "source_files": pins,
    }


def inspect_candidate(patch_path: Path, test_path: Path) -> dict[str, object]:
    patch_pin = pin(patch_path, EXPECTED_PATCH_SHA256)
    test_pin = pin(test_path, EXPECTED_HOOK_TEST_SHA256)
    patch = patch_path.read_text(encoding="utf-8")
    test = test_path.read_text(encoding="utf-8")
    for required in (
        "+    case PPC_INST_DCBST:",
        "PORTME(0x{:08X})",
        "PPC_DATA_CACHE_BLOCK_STORE((",
        'println("{}.u32), 128);"',
        "using PPCDataCacheStoreHook",
        "PPCFailFastDataCacheStoreHook",
        "std::abort();",
        "PPCSetDataCacheStoreHook",
        "effectiveAddress & ~(cacheLineSize - 1)",
        "if (cacheLineSize != 128)",
    ):
        require(required in patch, f"candidate patch contract changed: {required}")
    require("+    case PPC_INST_DCBF:" not in patch and
            patch.count("+    case PPC_INST_DCBST:") == 1,
            "candidate patch scope changed")
    for required in (
        "PPC_DATA_CACHE_BLOCK_STORE((ra + rb), 128)",
        "PPC_DATA_CACHE_BLOCK_STORE((rbOnly), 128)",
        "PPCSetDataCacheStoreHook(nullptr)",
        "WTERMSIG(status) == SIGABRT",
        "RunAndExpectAbort(base, 64)",
    ):
        require(required in test, f"hook test contract changed: {required}")
    return {
        "patch": patch_pin,
        "hook_test": test_pin,
        "applied_to_vendor": False,
        "runtime_overridable": True,
        "default_policy": "abort",
        "null_install_policy": "restore_abort_default",
        "hook_arguments": [
            "host_guest_memory_base",
            "exact_guest_effective_address",
            "aligned_guest_cache_line_address",
            "cache_line_size",
        ],
        "accepted_cache_line_size": 128,
        "line_alignment": "effective_address & ~127",
        "address_specific_portme_emitted": True,
        "dcbf_existing_no_op_changed": False,
        "ready_to_merge": False,
    }


def parse_observation(path: Path) -> dict[str, object]:
    observation = json.loads(path.read_text(encoding="utf-8"))
    require(observation.get("schema") == OBSERVATION_SCHEMA,
            "candidate observation schema changed")
    expected_scalars = {
        "candidate_patch_applied_in_temporary_copy": True,
        "patched_recompiler_syntax_pass": True,
        "patched_recompiler_link_pass": True,
        "translation_completed": True,
        "translation_log_terminal": "Recompiling functions... 100%",
        "unrecognized_instruction_count_before": 172,
        "unrecognized_instruction_count_after": 171,
        "dcbst_omission_count_before": 1,
        "dcbst_omission_count_after": 0,
        "generated_cpp_count": 237,
        "generated_numbered_cpp_count": 236,
        "generated_dcbst_hook_call_count": 1,
        "generated_address_specific_portme_count": 1,
        "generated_site_unit": "ppc_recomp.191.cpp",
        "generated_site_function": "0x84B464D8",
        "generated_site_address": "0x84B46518",
        "generated_site_hook_line": (
            "PPC_DATA_CACHE_BLOCK_STORE((ctx.r11.u32 + ctx.r9.u32), 128);"
        ),
        "generated_site_portme_line": EXPECTED_SITE_PORTME,
        "syntax_checked_cpp_count": 237,
        "syntax_failure_count": 0,
        "hook_test_exit_code": 0,
        "hook_test_stdout": EXPECTED_HOOK_STDOUT,
        "hook_test_stderr_empty": True,
        "default_hook_signal": "SIGABRT",
        "invalid_line_size_signal": "SIGABRT",
        "title_code_executed": False,
        "vendor_or_baseline_modified": False,
    }
    for key, value in expected_scalars.items():
        require(observation.get(key) == value,
                f"candidate observation changed: {key}")
    require(observation.get("unrecognized_mnemonic_counts_after") ==
            EXPECTED_AFTER_COUNTS,
            "post-candidate unrecognized counts changed")
    require(sum(EXPECTED_AFTER_COUNTS.values()) == 171,
            "internal post-candidate count mismatch")
    return observation


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xex", type=Path,
        default=Path("extracted/All-Pro Football 2K8 (USA)/default.xex"))
    parser.add_argument(
        "--decoded-tsv", type=Path,
        default=Path("reports/static_recomp/apf2k8_opcode_gap_decoded.tsv"))
    parser.add_argument(
        "--generated-unit", type=Path,
        default=Path("build-static-recomp-apf/ppc-filtered/ppc_recomp.191.cpp"))
    parser.add_argument("--vendor-root", type=Path,
                        default=Path("tools/vendor/XenonRecomp"))
    parser.add_argument(
        "--xenia-root", type=Path,
        default=Path("/media/noah/Storage/.codex-tmp/xenia-source"))
    parser.add_argument(
        "--candidate-patch", type=Path,
        default=Path("reports/static_recomp/apf2k8_dcbst_candidate.patch"))
    parser.add_argument(
        "--hook-test", type=Path,
        default=Path("tests/apf_dcbst_hook_test.cpp"))
    parser.add_argument("--candidate-observation", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    def resolve(path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    xex = resolve(args.xex)
    decoded = resolve(args.decoded_tsv)
    baseline_unit = resolve(args.generated_unit)
    vendor = resolve(args.vendor_root)
    xenia = resolve(args.xenia_root)
    patch = resolve(args.candidate_patch)
    hook_test = resolve(args.hook_test)
    observation_path = resolve(args.candidate_observation)
    output = resolve(args.json)
    for path in (xex, decoded, baseline_unit, patch, hook_test,
                 observation_path):
        require(path.is_file(), f"required file missing: {path}")
    for path in (vendor, xenia):
        require(path.is_dir(), f"required source tree missing: {path}")

    xex_pin = pin(xex, EXPECTED_XEX_SHA256)
    require(git_head(vendor) == EXPECTED_VENDOR_COMMIT,
            "pinned XenonRecomp commit changed")
    require_tracked_clean(vendor)
    recompiler = vendor / "XenonRecomp/recompiler.cpp"
    context = vendor / "XenonUtils/ppc_context.h"
    recompiler_pin = pin(recompiler, EXPECTED_RECOMPILER_SHA256)
    context_pin = pin(context, EXPECTED_CONTEXT_SHA256)
    require("case PPC_INST_DCBST:" not in recompiler.read_text(encoding="utf-8"),
            "candidate unexpectedly present in vendor")

    site = parse_site(decoded)
    baseline = inspect_baseline(baseline_unit)
    xenia_evidence = inspect_xenia(xenia)
    candidate = inspect_candidate(patch, hook_test)
    observation = parse_observation(observation_path)

    address_portme = EXPECTED_SITE_PORTME
    report = {
        "schema": SCHEMA,
        "result": {
            "dcbst_site_count": 1,
            "containing_function_count": 1,
            "exact_ra0_effective_address_emission_proved": True,
            "xenon_128_byte_line_contract_proved": True,
            "runtime_overridable_hook_present_in_candidate": True,
            "default_hook_fail_fast_proved": True,
            "invalid_line_size_fail_fast_proved": True,
            "dcbst_omission_count_after_isolated_regeneration": 0,
            "generated_translation_units_syntax_passed": 237,
            "candidate_applied_to_vendor": False,
            "gpu_dma_mmio_visibility_policy_implemented": False,
            "architecture_complete_runtime_proved": False,
            "title_code_executed": False,
        },
        "official_ibm_semantics": {
            "source": IBM_DCBST_URL,
            "purpose": "copy a modified cache block to main memory",
            "effective_address": "RA != 0 ? GPR[RA] + GPR[RB] : GPR[RB]",
            "target": "cache block containing the byte addressed by EA",
            "translation_and_protection": "treat as a load from the addressed byte",
            "fixed_point_exception_register_affected": False,
            "generic_powerpc_source_defines_xenon_line_size": False,
        },
        "pinned_xenia": xenia_evidence,
        "apf_site": {
            **site,
            **baseline,
            "range_loop": (
                "r9 is the 128-byte-aligned start; r11 begins at zero and "
                "increments by 128 before looping while r11 < r10"
            ),
            "candidate_generated_expression":
                observation["generated_site_hook_line"],
            "candidate_generated_portme": address_portme,
        },
        "candidate_contract": candidate,
        "isolated_validation": observation,
        "runtime_policy_boundary": {
            "coherent_flat_host_ram_visibility_no_op_permitted": True,
            "no_op_preconditions": [
                "guest address translation/protection has been validated as a load",
                "all CPU, GPU, DMA, and MMIO consumers observe the same coherent storage",
                "required ordering is supplied by the surrounding guest/runtime barriers",
            ],
            "gpu_dma_mmio_policy_currently_implemented": False,
            "alternate_dcbf_at_0x84B464F8_currently_hooked": False,
            "why_default_aborts": (
                "silently returning would assert a coherency/protection policy "
                "that the current runtime has not proved"
            ),
        },
        "sources": {
            "retail_xex": xex_pin,
            "decoded_site_table": pin(decoded, EXPECTED_DECODED_TSV_SHA256),
            "baseline_generated_unit": pin(
                baseline_unit, EXPECTED_BASELINE_UNIT_SHA256),
            "vendor_recompiler": recompiler_pin,
            "vendor_context": context_pin,
            "generator": pin(Path(__file__).resolve()),
            "candidate_observation_embeds_title_bytes": False,
        },
        "interpretation": {
            "worked": [
                "Closed the sole dcbst translator omission in an unapplied candidate.",
                "Matched IBM RA0 EA semantics and pinned Xenia's 128-byte DATA_STORE model.",
                "Proved the candidate emits uint32(r11+r9) at 0x84B46518.",
                "Proved runtime hook override, line alignment, aborting default, and invalid-size abort.",
                "Regenerated APF and syntax-checked all 237 generated C++ translation units.",
            ],
            "failed_or_unproved": [
                "No guest GPU/DMA/MMIO visibility implementation is installed.",
                "IBM load-like translation/protection behavior remains a runtime hook duty.",
                "The alternate dcbf branch remains XenonRecomp's pre-existing no-op.",
                "Static context does not prove boot or gameplay reachability.",
            ],
            "blocking": [
                "Choose and implement the guest memory visibility/protection policy.",
                "Route dcbf through a distinct store-and-invalidate policy before claiming the whole cache-range helper complete.",
            ],
        },
        "portme": [
            address_portme,
            "// PORTME(0x84B464F8): replace the existing dcbf no-op with a distinct 128-byte store-and-invalidate runtime policy.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_DCBST_SEMANTICS_PASS site=0x84B46518 ea=RA0 line=128 "
        "hook=runtime default=abort omission_after=0 tus=237 runtime_policy=PORTME "
        "title_executed=no"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DcbstError, OSError, ValueError, KeyError, struct.error,
            subprocess.SubprocessError) as exc:
        raise SystemExit(f"error: {exc}") from exc
