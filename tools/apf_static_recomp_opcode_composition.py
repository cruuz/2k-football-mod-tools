#!/usr/bin/env python3
"""Compose and audit APF's three isolated XenonRecomp opcode candidates.

The tool never patches the pinned vendor tree.  It deterministically rebuilds
the composed patch byte stream from the three reviewed isolated patches and
turns a validator-produced, title-free regeneration observation into a pinned
JSON report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


SCHEMA = "apf2k8_static_recomp_opcode_composition/v1"
OBSERVATION_SCHEMA = "apf2k8_static_recomp_opcode_composition_observation/v1"
EXPECTED_VENDOR_COMMIT = "ddd128bcca99fe8bfbb99bea583c972351fa6ace"
EXPECTED_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_VOLUME_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)
EXPECTED_RECOMPILER_SHA256 = (
    "30e7ea5b4d8a225bc3e0ac71aebd1a0af7bcde5aaf5679517719b559c9cd777a"
)
EXPECTED_CONTEXT_SHA256 = (
    "369acaf639c52bb25ee8a2c6a555c7875912f0692b1e8220ea8dab0384e42263"
)
EXPECTED_BASELINE_TREE_SHA256 = (
    "1a0264262be8cc48e44e56c7c87c3a0f77def90dd62d40ea9842d174baed5fd1"
)
EXPECTED_COMPOSED_TREE_SHA256 = (
    "d89dafb93dc91d614199766645fd254e34e6b939151dcc890773688e3e18f809"
)
EXPECTED_COMPOSED_RECOMPILER_SHA256 = (
    "b12b0cd01f0d29c0d0eff00d145289789d0051b2091f3176a732e8607ca44020"
)
EXPECTED_COMPOSED_CONTEXT_SHA256 = (
    "0c217483f60a4c70d15de1a2ac3a652bf753fc183c2deef4f04b1f8a4727ba52"
)
EXPECTED_COMPOSED_PATCH_SHA256 = (
    "5a6f15ebb3ff6c0ae2735e370b04e93033cd6d493be0a7a2697379d63e6f26bd"
)
EXPECTED_CONFIG_SHA256 = (
    "bc9fb745b7f5d43dbb9e8ec0bc14058590c825fb51a14d5474c3aa44ef74372c"
)
EXPECTED_SWITCHES_SHA256 = (
    "12e6d83752dfee30da4c1797fcfea63d2a832c8bee5968d4e4b3603be223c988"
)
EXPECTED_BASELINE_PROBE_SHA256 = (
    "e437f353a0f3ee909e71728e6975ed5b9530ee7f2736c447058dc88d88bf3e1f"
)
EXPECTED_DCBST_HOOK_TEST_SHA256 = (
    "21155e45fe713f0e6a25f538dfce206891f4c17a3505054c50004d7791b15b26"
)

ISOLATED_PATCHES = (
    (
        "reports/static_recomp/apf2k8_opcode_gap_candidate.patch",
        "4ebeae411d794ad9552cb008d9744d01d1273eda70bf218cbe73df05e3081495",
        143,
    ),
    (
        "reports/static_recomp/apf2k8_frsqrte_candidate.patch",
        "9b2d5248fa8e9bb8e93e161fc7f86f0eeaaae2803d392596769d3d8d82c83396",
        28,
    ),
    (
        "reports/static_recomp/apf2k8_dcbst_candidate.patch",
        "018ce6f0fe2596b59606cfd85eb77648eaa32fcecab7ff78a213ac2128847de1",
        1,
    ),
)

SOURCE_REPORTS = (
    (
        "reports/static_recomp/apf2k8_opcode_gap_audit.json",
        "39b219785aed7bccd909a0ebe5b1a45115672bb73384aff68d94612bc077fc6c",
        "apf2k8_static_recomp_opcode_audit/v1",
    ),
    (
        "reports/static_recomp/apf2k8_frsqrte_semantics.json",
        "80bdb2fc5c0065cfb76b173572b721262b288f5fc2974301f4221832023d4707",
        "apf2k8_frsqrte_semantics/v1",
    ),
    (
        "reports/static_recomp/apf2k8_dcbst_semantics.json",
        "095bf63169e2c91357c6733c1cecb664b496d464bc3934216a92d01708f18af7",
        "apf2k8_dcbst_semantics/v1",
    ),
)

EXPECTED_MNEMONIC_COUNTS = {
    "dcbst": 1,
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


class CompositionError(RuntimeError):
    """Raised when a pinned input or composition invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompositionError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            state.update(block)
    return state.hexdigest()


def relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def pin(root: Path, path: Path, expected: str | None = None) -> dict[str, object]:
    digest = sha256_file(path)
    if expected is not None:
        require(digest == expected, f"pinned file changed: {path}")
    return {
        "path": relative(root, path),
        "size": path.stat().st_size,
        "sha256": digest,
    }


def git_head(path: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    require(completed.returncode == 0, f"not a git tree: {path}")
    return completed.stdout.strip()


def require_tracked_clean(path: Path) -> None:
    for arguments in (
        ("diff", "--quiet", "HEAD", "--"),
        ("diff", "--cached", "--quiet", "HEAD", "--"),
    ):
        completed = subprocess.run(
            ["git", "-C", str(path), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        require(completed.returncode == 0, f"tracked vendor source changed: {path}")


def flat_tree_manifest(directory: Path) -> tuple[int, str]:
    files = sorted((path for path in directory.iterdir() if path.is_file()),
                   key=lambda path: path.name)
    manifest = b"".join(
        f"{sha256_file(path)}  {path.name}\n".encode("utf-8") for path in files
    )
    return len(files), sha256_bytes(manifest)


def load_source_reports(root: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    reports: list[dict[str, object]] = []
    loaded: dict[str, dict[str, object]] = {}
    for name, expected_hash, schema in SOURCE_REPORTS:
        path = root / name
        source = json.loads(path.read_text(encoding="utf-8"))
        require(source.get("schema") == schema, f"source report schema changed: {name}")
        reports.append(pin(root, path, expected_hash))
        loaded[schema] = source

    audit = loaded["apf2k8_static_recomp_opcode_audit/v1"]
    require(audit["result"]["site_count"] == 172,
            "baseline opcode site count changed")
    require(audit["result"]["candidate_patch_data_state_site_count"] == 143,
            "isolated data/state candidate count changed")
    require(audit["candidate_patch_validation"]["unsupported_site_count_after"] == 29,
            "isolated data/state remainder changed")

    frsqrte = loaded["apf2k8_frsqrte_semantics/v1"]
    require(frsqrte["result"]["site_count"] == 28,
            "frsqrte site count changed")
    require(frsqrte["result"]["architecture_complete_site_count"] == 0,
            "frsqrte architecture boundary changed")
    require(frsqrte["candidate_patch"]["ready_to_merge"] is False,
            "frsqrte candidate unexpectedly became merge-ready")

    dcbst = loaded["apf2k8_dcbst_semantics/v1"]
    require(dcbst["result"]["dcbst_site_count"] == 1,
            "dcbst site count changed")
    require(dcbst["result"]["gpu_dma_mmio_visibility_policy_implemented"] is False,
            "dcbst runtime-policy boundary changed")
    require(dcbst["candidate_contract"]["dcbf_existing_no_op_changed"] is False,
            "dcbf boundary changed")
    return reports, loaded


def compose_patch(root: Path, output: Path) -> tuple[list[dict[str, object]], bytes]:
    parts: list[bytes] = []
    pins: list[dict[str, object]] = []
    for name, expected_hash, _ in ISOLATED_PATCHES:
        path = root / name
        pins.append(pin(root, path, expected_hash))
        parts.append(path.read_bytes().rstrip(b"\n"))
    composed = b"\n\n".join(parts) + b"\n"
    require(sha256_bytes(composed) == EXPECTED_COMPOSED_PATCH_SHA256,
            "deterministic composed-patch digest changed")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(composed)
    return pins, composed


def inspect_patch(composed: bytes) -> dict[str, object]:
    text = composed.decode("utf-8")
    case_names = (
        "MULHDU", "STFSU", "VADDSWS", "VANDC", "VPKSWSS", "VRFIP",
        "VSEL128", "VSRAB", "VSUBUWM", "FRSQRTE", "DCBST",
    )
    for name in case_names:
        require(text.count(f"+    case PPC_INST_{name}:") == 1,
                f"composed case multiplicity changed: {name}")
    require(text.count("PORTME: update sticky VSCR.SAT") == 2,
            "VSCR.SAT caveat count changed")
    require("PPC_FRSQRTE_XENIA_6E5B832_VALUE" in text,
            "frsqrte helper missing from composition")
    require("PPC_DATA_CACHE_BLOCK_STORE" in text,
            "dcbst runtime hook missing from composition")
    require("switch_tail" not in text.lower() and
            "PPC_SWITCH_TAIL_DISPATCH" not in text,
            "switch-tail candidate leaked into opcode-only composition")
    return {
        "isolated_patch_order": [name for name, _, _ in ISOLATED_PATCHES],
        "concatenation_rule": (
            "strip trailing LF from each isolated patch, join in listed order "
            "with two LF bytes, append one final LF"
        ),
        "case_count": len(case_names),
        "switch_tail_candidate_included": False,
    }


def load_observation(path: Path) -> dict[str, object]:
    observation = json.loads(path.read_text(encoding="utf-8"))
    require(observation.get("schema") == OBSERVATION_SCHEMA,
            "composition observation schema changed")
    expected = {
        "candidate_patch_applied_in_temporary_copy": True,
        "patched_recompiler_syntax_pass": True,
        "patched_recompiler_link_pass": True,
        "translation_completed": True,
        "translation_log_terminal": "Recompiling functions... 100%",
        "unrecognized_instruction_count_before": 172,
        "unrecognized_instruction_count_after": 0,
        "generated_file_count": 240,
        "generated_cpp_count": 237,
        "generated_numbered_cpp_count": 236,
        "generated_translation_units_syntax_checked": 237,
        "generated_translation_unit_syntax_failure_count": 0,
        "data_state_candidate_site_count": 143,
        "frsqrte_candidate_site_count": 28,
        "dcbst_candidate_site_count": 1,
        "composed_candidate_site_count": 172,
        "frsqrte_helper_call_count": 28,
        "dcbst_hook_call_count": 1,
        "dcbst_address_portme_count": 1,
        "switch_outside_function_error_count": 3337,
        "switch_base_with_error_count": 196,
        "output_manifest_sha256": EXPECTED_COMPOSED_TREE_SHA256,
        "composed_recompiler_sha256": EXPECTED_COMPOSED_RECOMPILER_SHA256,
        "composed_context_sha256": EXPECTED_COMPOSED_CONTEXT_SHA256,
        "dcbst_hook_test_exit_code": 0,
        "dcbst_hook_test_stderr_empty": True,
        "title_code_executed": False,
        "vendor_originals_or_baseline_modified": False,
        "switch_tail_candidate_composed": False,
    }
    for key, value in expected.items():
        require(observation.get(key) == value,
                f"composition observation changed: {key}")
    require(observation.get("generated_mnemonic_comment_counts") ==
            EXPECTED_MNEMONIC_COUNTS,
            "generated mnemonic coverage changed")
    require(sum(EXPECTED_MNEMONIC_COUNTS.values()) == 172,
            "internal mnemonic total changed")
    require(observation.get("unrecognized_mnemonic_counts_after") == {},
            "post-composition opcode omissions appeared")
    require(observation.get("dcbst_hook_test_stdout") == (
        "APF_DCBST_HOOK_TEST_PASS nonzero_ra_ea=0x00000145 "
        "nonzero_ra_line=0x00000100 rb_only_ea=0x00ABCDEF "
        "rb_only_line=0x00ABCD80 line_size=128 default_signal=6 "
        "invalid_size_signal=6\n"
    ), "combined dcbst hook contract changed")
    return observation


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xex", type=Path,
        default=Path("extracted/All-Pro Football 2K8 (USA)/default.xex"))
    parser.add_argument(
        "--volume", type=Path,
        default=Path("extracted/All-Pro Football 2K8 (USA)/0A"))
    parser.add_argument(
        "--vendor-root", type=Path,
        default=Path("tools/vendor/XenonRecomp"))
    parser.add_argument(
        "--baseline-generated", type=Path,
        default=Path("build-static-recomp-apf/ppc-filtered"))
    parser.add_argument(
        "--config", type=Path,
        default=Path("reports/static_recomp/apf2k8_xenonrecomp_filtered_probe.toml"))
    parser.add_argument(
        "--switches", type=Path,
        default=Path("reports/static_recomp/apf2k8_xenon_switch_tables_filtered.toml"))
    parser.add_argument(
        "--baseline-probe", type=Path,
        default=Path("reports/static_recomp/apf2k8_static_recomp_probe.json"))
    parser.add_argument(
        "--dcbst-hook-test", type=Path,
        default=Path("tests/apf_dcbst_hook_test.cpp"))
    parser.add_argument(
        "--committed-composed-patch", type=Path,
        default=Path("reports/static_recomp/apf2k8_opcode_candidates_composed.patch"))
    parser.add_argument("--candidate-observation", type=Path, required=True)
    parser.add_argument("--reconstructed-patch", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()

    def resolve(path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    xex = resolve(args.xex)
    volume = resolve(args.volume)
    vendor = resolve(args.vendor_root)
    baseline = resolve(args.baseline_generated)
    config = resolve(args.config)
    switches = resolve(args.switches)
    baseline_probe = resolve(args.baseline_probe)
    dcbst_hook_test = resolve(args.dcbst_hook_test)
    committed_patch = resolve(args.committed_composed_patch)
    observation_path = resolve(args.candidate_observation)
    reconstructed_patch = resolve(args.reconstructed_patch)
    output = resolve(args.json)
    for path in (xex, volume, config, switches, baseline_probe,
                 dcbst_hook_test, committed_patch, observation_path):
        require(path.is_file(), f"required file missing: {path}")
    for path in (vendor, baseline):
        require(path.is_dir(), f"required directory missing: {path}")

    require(git_head(vendor) == EXPECTED_VENDOR_COMMIT,
            "XenonRecomp commit changed")
    require_tracked_clean(vendor)
    xex_pin = pin(root, xex, EXPECTED_XEX_SHA256)
    volume_pin = pin(root, volume, EXPECTED_VOLUME_SHA256)
    recompiler_pin = pin(
        root, vendor / "XenonRecomp/recompiler.cpp", EXPECTED_RECOMPILER_SHA256)
    context_pin = pin(
        root, vendor / "XenonUtils/ppc_context.h", EXPECTED_CONTEXT_SHA256)
    config_pin = pin(root, config, EXPECTED_CONFIG_SHA256)
    switches_pin = pin(root, switches, EXPECTED_SWITCHES_SHA256)
    baseline_probe_pin = pin(
        root, baseline_probe, EXPECTED_BASELINE_PROBE_SHA256)
    dcbst_hook_test_pin = pin(
        root, dcbst_hook_test, EXPECTED_DCBST_HOOK_TEST_SHA256)
    baseline_count, baseline_digest = flat_tree_manifest(baseline)
    require(baseline_count == 240 and
            baseline_digest == EXPECTED_BASELINE_TREE_SHA256,
            "baseline generated corpus changed")

    source_report_pins, _ = load_source_reports(root)
    isolated_patch_pins, reconstructed = compose_patch(root, reconstructed_patch)
    committed_pin = pin(root, committed_patch, EXPECTED_COMPOSED_PATCH_SHA256)
    require(committed_patch.read_bytes() == reconstructed,
            "committed composed patch is not the deterministic composition")
    patch_contract = inspect_patch(reconstructed)
    observation = load_observation(observation_path)

    portme = [
        "// PORTME: model sticky VSCR.SAT for all 57 saturating VMX sites before architecture-complete use.",
        "// PORTME: validate all 28 frsqrte sites against a dense Xenon hardware oracle and implement FPSCR, NI, and enabled exceptions.",
        "// PORTME(0x84B46518): implement load-like protection plus GPU/DMA/MMIO visibility for dcbst.",
        "// PORTME(0x84B464F8): replace the existing dcbf no-op with a distinct store-and-invalidate runtime policy.",
        "// PORTME: resolve the 3,337 switch-tail boundary diagnostics at 196 switch bases independently of opcode coverage.",
    ]
    report = {
        "schema": SCHEMA,
        "result": {
            "baseline_unrecognized_instruction_site_count": 172,
            "composed_unrecognized_instruction_site_count": 0,
            "all_baseline_opcode_omissions_have_candidate_emission": True,
            "data_state_candidate_site_count": 143,
            "frsqrte_candidate_site_count": 28,
            "dcbst_candidate_site_count": 1,
            "composed_candidate_site_count": 172,
            "generated_cpp_count": 237,
            "generated_translation_units_syntax_passed": 237,
            "candidate_applied_to_vendor": False,
            "title_code_executed": False,
            "architecture_complete": False,
            "ready_to_merge": False,
        },
        "composition": {
            **patch_contract,
            "isolated_patch_site_counts": [
                {"path": name, "site_count": count}
                for name, _, count in ISOLATED_PATCHES
            ],
            "composed_patch": committed_pin,
            "composed_source_hashes_after_temporary_apply": {
                "XenonRecomp/recompiler.cpp": EXPECTED_COMPOSED_RECOMPILER_SHA256,
                "XenonUtils/ppc_context.h": EXPECTED_COMPOSED_CONTEXT_SHA256,
            },
            "applied_to_pinned_vendor": False,
        },
        "regeneration": observation,
        "semantic_boundaries": {
            "saturating_vmx": {
                "site_count": 57,
                "lane_data_candidate_present": True,
                "sticky_vscr_sat_implemented": False,
            },
            "frsqrte": {
                "site_count": 28,
                "pinned_xenia_ieee_value_candidate_present": True,
                "dense_xenon_hardware_oracle": False,
                "fpscr_ni_enabled_exceptions_implemented": False,
            },
            "dcbst": {
                "site_count": 1,
                "runtime_hook_candidate_present": True,
                "default_policy": "abort",
                "gpu_dma_mmio_and_protection_policy_implemented": False,
                "alternate_dcbf_policy_implemented": False,
            },
            "control_flow": {
                "switch_tail_candidate_included": False,
                "outside_function_diagnostics_in_opcode_only_regeneration": 3337,
                "affected_switch_bases": 196,
                "opcode_coverage_implies_control_flow_complete": False,
            },
        },
        "sources": {
            "retail_xex": xex_pin,
            "retail_volume_0A": volume_pin,
            "vendor_commit": EXPECTED_VENDOR_COMMIT,
            "vendor_recompiler": recompiler_pin,
            "vendor_context": context_pin,
            "filtered_recompiler_config": config_pin,
            "filtered_switch_table": switches_pin,
            "baseline_probe": baseline_probe_pin,
            "dcbst_hook_test": dcbst_hook_test_pin,
            "baseline_generated_tree": {
                "path": relative(root, baseline),
                "file_count": baseline_count,
                "manifest_sha256": baseline_digest,
            },
            "isolated_patches": isolated_patch_pins,
            "isolated_reports": source_report_pins,
            "generator": pin(root, Path(__file__).resolve()),
            "report_embeds_title_bytes": False,
        },
        "interpretation": {
            "worked": [
                "The three isolated patches apply together without source conflicts.",
                "A complete APF regeneration reduced 172 opcode-omission messages to zero.",
                "All 237 generated C++ translation units passed Clang syntax checks.",
                "The combined generated header retained the tested fail-fast dcbst hook contract.",
            ],
            "failed_or_unproved": [
                "Zero opcode omissions does not prove architecture-correct instruction behavior.",
                "VSCR.SAT, dense Xenon frsqrte/FPSCR/NI behavior, and dcbst device coherency remain unimplemented.",
                "The opcode-only regeneration still reports 3,337 switch-tail function-boundary diagnostics at 196 switch bases.",
                "No translated title code was linked or executed.",
            ],
            "blocking": [
                "Resolve and validate switch-tail control-flow boundaries separately.",
                "Implement and differentially validate every semantic boundary listed above.",
                "Compose only reviewed runtime/import/memory work before attempting a title bootstrap.",
            ],
        },
        "portme": portme,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_STATIC_RECOMP_OPCODE_COMPOSITION_PASS before=172 after=0 "
        "candidates=143+28+1 tus=237 syntax=pass switch_errors=3337 "
        "architecture_complete=no vendor_unchanged=yes title_executed=no"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CompositionError, OSError, ValueError, KeyError,
            subprocess.SubprocessError) as exc:
        raise SystemExit(f"error: {exc}") from exc
