#!/usr/bin/env python3
"""Verify the retained Group 36 runtime receipt with virtual XISO products.

The two historical runtime XISOs were intentionally cleaned.  This tool pins
every retained receipt artifact, reconstructs both final images while hashing
the retail source, and proves their historical SHA-256 identities without
writing either image or launching an emulator.  Runtime observations remain
bounded to the immutable screenshots/report and incomplete QCOW2 lineage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

import nfl_uniform_color_xiso_direct_patch as xiso


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/assets/nfl2k5_group36_s42_xemu_runtime_positive.v2.json"
SOURCE = ROOT / "ESPN NFL 2K5 (USA).xiso.iso"
GEOMETRY_VOLUME = ROOT / ".geometry-proof/expanded-wall-output/9"
BUILD = ROOT / "build/nfl2k5-stadium-group36-geometry-xiso-20260713"

REPORT_PIN = (
    12_051,
    "33d76b3bbc9d11b52af6cf2861cf2890574a6d5b6820df8972d8419a63459d60",
)
SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
GEOMETRY_SHA256 = "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad"
CONTROL_SHA256 = "863ba00df855efdf54b85d568516b1ed0f7bbd33ddb77096ce3e16da4e702383"
EXPANDED_SHA256 = "d41c44882919a00282c184fcc85b4ec139e17b48ee7681960808cc14947bab72"

WORKFLOW_PINS = {
    "expanded-wall-workflow.json": (
        3_062, "80a5361c8b514f7215683d7ae7afdf91a365f4ac64d1736ba76ba349c9d69f95",
    ),
    "s42-dispatch-control-workflow.json": (
        3_659, "e619cf3fa5eae3eea4a09e97f681db96df968041c6746dda68a013dd6ddbef89",
    ),
    "expanded-wall-s42-dispatch-workflow.json": (
        4_577, "4fd1d53323c39cef94d7b5ac2a17a4c7d8669abff126f83a5eeda8a451b3e5c0",
    ),
    "s42-visible-control-workflow.json": (
        6_701, "88b4e1e0a5911ba7c2fa6b92d61eaf5b7b47605d9a61d4208cffbbcb1eefbdbe",
    ),
    "expanded-wall-s42-visible-workflow.json": (
        6_808, "166ba6a28318e289446f0814edd9bcddb28360bd4ad16b13dfa22f82634429b7",
    ),
    "s42-visible-night-control-workflow.json": (
        7_227, "cb503cc117909eb78048dc96f68a1b1ccd12c6223781eba6742e6a0c12cff5db",
    ),
    "expanded-wall-s42-visible-night-workflow.json": (
        7_287, "a003d7f04e23c291e28c577923d332080f74bca8a749881972325a82f285a97b",
    ),
}

PACK9_OFFSET = 72_767_488
PACK9_SIZE = 634_941_440
GEOMETRY_SPAN_OFFSET = 132_799_040
GEOMETRY_SPAN_SIZE = 908_912
GEOMETRY_ABSOLUTE = 205_566_528
DISPATCH_ALLOCATION = 1_635_418_434
ASSET_BEFORE = ("s18\0").encode("utf-16le")
ASSET_AFTER = ("s42\0").encode("utf-16le")
TEXT_DIGEST_ABSOLUTE = 2_397_076
TEXT_SOURCE_DIGEST = bytes.fromhex("72edb599858a06a0f88c6ae446907e3977f4fec6")
TEXT_OUTPUT_DIGEST = bytes.fromhex("a013179864b328a3bda23b60f4cee9b9ed7dcc9d")
TIME_DISPLACEMENT_ABSOLUTE = 2_735_201
DATA_DIGEST_ABSOLUTE = 2_397_804
DATA_SOURCE_DIGEST = bytes.fromhex("8c86ae03ba27ffd03d09a3b8ca21d61e74a9337c")
DATA_OUTPUT_DIGEST = bytes.fromhex("8011736208bf6320358ee1b1cdaf29d421f80c24")
UNLOCK_ABSOLUTE = 13_457_596
UNLOCK_BEFORE = struct.pack("<I", 0x14B)
UNLOCK_AFTER = struct.pack("<I", 0)
DEFAULT_XBE_OFFSET = 1_170 * 2_048
DEFAULT_XBE_SIZE = 11_948_032
FINAL_XBE_SHA256 = "c6abdd77be89594ee19dbfd8dbfa300b592a5a2ed1af2276e5e132678e50cc27"


class ReceiptError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReceiptError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def open_regular(path: Path, expected_size: int, label: str) -> tuple[int, tuple[int, int, int]]:
    supplied = path.lstat()
    require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode)
        and supplied.st_size == expected_size,
        f"{label} is not the expected regular non-symlink file",
    )
    descriptor = os.open(
        path.resolve(strict=True),
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    opened = os.fstat(descriptor)
    identity = (opened.st_dev, opened.st_ino, opened.st_size)
    require(
        stat.S_ISREG(opened.st_mode)
        and identity == (supplied.st_dev, supplied.st_ino, supplied.st_size),
        f"{label} identity changed before opening",
    )
    return descriptor, identity


def close_unchanged(path: Path, descriptor: int, identity: tuple[int, int, int], label: str) -> None:
    try:
        current = path.stat(follow_symlinks=False)
        require(
            (current.st_dev, current.st_ino, current.st_size) == identity,
            f"{label} changed while open",
        )
    finally:
        os.close(descriptor)


def read_pinned_json(path: Path, pin: tuple[int, str], label: str) -> dict[str, Any]:
    descriptor, identity = open_regular(path, pin[0], label)
    try:
        raw = xiso.read_exact(descriptor, 0, pin[0])
        require(digest(raw) == pin[1], f"{label} SHA-256 differs")
        value = json.loads(raw)
        require(
            isinstance(value, dict)
            and raw == (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(),
            f"{label} is not canonical JSON",
        )
        return value
    finally:
        close_unchanged(path, descriptor, identity, label)


def resolve_record(record: dict[str, Any]) -> Path:
    path = Path(record["path"])
    return path if path.is_absolute() else ROOT / path


def pin_record(record: dict[str, Any], label: str) -> None:
    path = resolve_record(record)
    descriptor, identity = open_regular(path, int(record["size"]), label)
    try:
        hasher = hashlib.sha256()
        remaining = identity[2]
        while remaining:
            block = os.read(descriptor, min(16 * 1024 * 1024, remaining))
            require(block, f"short {label} read")
            hasher.update(block)
            remaining -= len(block)
        require(hasher.hexdigest() == record["sha256"], f"{label} SHA-256 differs")
    finally:
        close_unchanged(path, descriptor, identity, label)


def pin_retained_report_artifacts(report: dict[str, Any]) -> None:
    omitted = {
        report["offline_proof"]["expanded_geometry_volume"]["path"],
        report["runs"]["control"]["artifacts"]["xiso"]["path"],
        report["runs"]["expanded_wall"]["artifacts"]["xiso"]["path"],
    }
    seen: dict[str, tuple[int, str]] = {}

    def walk(value: object, label: str) -> None:
        if isinstance(value, dict):
            if {"path", "size", "sha256"} <= value.keys():
                path = str(value["path"])
                identity = (int(value["size"]), str(value["sha256"]))
                require(path not in seen or seen[path] == identity,
                        f"conflicting receipt records for {path}")
                if path not in omitted and path not in seen:
                    pin_record(value, label)
                seen[path] = identity
            for key, child in value.items():
                walk(child, f"{label}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{label}[{index}]")

    walk(report, "report")
    for name in ("control", "expanded_wall"):
        screenshots = report["runs"][name]["artifacts"]["screenshots"]
        for row in screenshots:
            path = resolve_record(row)
            with path.open("rb") as stream:
                header = stream.read(24)
            dimensions = (1280, 672) if row["role"] == "geometry_frame" else (1280, 720)
            require(
                len(header) == 24 and header[:8] == b"\x89PNG\r\n\x1a\n"
                and header[12:16] == b"IHDR"
                and struct.unpack(">II", header[16:24]) == dimensions,
                f"{name} {row['role']} PNG boundary differs",
            )


def validate_claim_boundary(report: dict[str, Any]) -> None:
    claims = report["claims"]
    true_claims = {
        "control_target_outer_loaded_proved",
        "diagnostic_only",
        "expanded_target_outer_loaded_proved",
        "geometry_visibility_proved",
        "geometry_visibility_scope_pinned_xemu_diagnostic_only",
        "s42_quick_game_selectability_proved",
        "same_camera_sequence_proved",
        "target_outer_loaded_proved",
        "xemu_boot_acceptance_proved",
        "xemu_clean_shutdown_pair_observed",
    }
    false_claims = {
        "changed_count_mesh_writeback_proved",
        "distribution_ready",
        "general_static_mesh_runtime_writeback_proved",
        "original_xbox_hardware_proved",
        "pixel_aligned_matched_pair_proved",
        "production_ready",
        "public_editor_exposed",
        "retail_signed_executable_chain_preserved",
        "runtime_gpu_trace_proved",
        "strict_v1_exact_frame_branch_satisfied",
    }
    require(set(claims) == true_claims | false_claims, "runtime claim key set differs")
    require(all(claims[key] is True for key in true_claims), "positive runtime claim differs")
    require(all(claims[key] is False for key in false_claims), "negative runtime boundary differs")
    camera = report["pair"]["camera_protocol"]
    require(
        camera["same_sequence"] is True and camera["end_zone_facing"] is True
        and camera["pixel_aligned"] is False and camera["same_play_state"] is False
        and camera["same_team_state"] is False,
        "runtime camera causal boundary differs",
    )
    require(
        report["runs"]["control"]["runtime"]["authored_wall_visible"] is False
        and report["runs"]["expanded_wall"]["runtime"]["authored_wall_visible"] is True,
        "control/expanded visual observation boundary differs",
    )
    for name in ("control", "expanded_wall"):
        runtime = report["runs"][name]["runtime"]
        require(runtime["clean_shutdown_observed"] is True and runtime["exit_code"] == 0
                and runtime["shutdown_method"] == "WM_DELETE_WINDOW",
                f"{name} retained shutdown receipt differs")


def validate_workflows(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    workflows = {
        name: read_pinned_json(BUILD / name, pin, name)
        for name, pin in WORKFLOW_PINS.items()
    }
    geometry = workflows["expanded-wall-workflow.json"]
    control_dispatch = workflows["s42-dispatch-control-workflow.json"]
    expanded_dispatch = workflows["expanded-wall-s42-dispatch-workflow.json"]
    control_visible = workflows["s42-visible-control-workflow.json"]
    expanded_visible = workflows["expanded-wall-s42-visible-workflow.json"]
    control_final = workflows["s42-visible-night-control-workflow.json"]
    expanded_final = workflows["expanded-wall-s42-visible-night-workflow.json"]

    require(
        geometry["schema"] == "nfl2k5_group36_geometry_xiso_patch/v1"
        and geometry["source"]["sha256_before"] == SOURCE_SHA256
        and geometry["output"]["sha256"]
        == expanded_dispatch["source"]["sha256_before"]
        == "a17ce0bd1f37d3c361245334586346a5f43b5a9374ffe05fe5e41b101a10137c",
        "geometry-to-dispatch workflow chain differs",
    )
    require(
        control_dispatch["source"]["sha256_before"] == SOURCE_SHA256
        and control_dispatch["output"]["sha256"]
        == control_visible["source"]["sha256_before"]
        == "32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5"
        and expanded_dispatch["output"]["sha256"]
        == expanded_visible["source"]["sha256_before"]
        == "3c2917114ec7005e21c24c7fdf971adfdd54c051e89ecf2c4f93beb64a73dc16",
        "dispatch-to-visibility workflow chain differs",
    )
    require(
        control_visible["output"]["sha256"]
        == control_final["source"]["sha256_before"]
        == "9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40"
        and expanded_visible["output"]["sha256"]
        == expanded_final["source"]["sha256_before"]
        == "f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6"
        and control_final["output"]["sha256"] == CONTROL_SHA256
        and expanded_final["output"]["sha256"] == EXPANDED_SHA256,
        "visibility-to-force-n workflow chain differs",
    )
    require(
        report["runs"]["control"]["artifacts"]["workflow_manifest"]["sha256"]
        == WORKFLOW_PINS["s42-visible-night-control-workflow.json"][1]
        and report["runs"]["expanded_wall"]["artifacts"]["workflow_manifest"]["sha256"]
        == WORKFLOW_PINS["expanded-wall-s42-visible-night-workflow.json"][1],
        "runtime report does not bind the final workflows",
    )

    dispatch_offsets = [DISPATCH_ALLOCATION + 2, DISPATCH_ALLOCATION + 4]
    visibility_offsets = list(range(DATA_DIGEST_ABSOLUTE, DATA_DIGEST_ABSOLUTE + 20)) + [
        UNLOCK_ABSOLUTE, UNLOCK_ABSOLUTE + 1,
    ]
    force_offsets = list(range(TEXT_DIGEST_ABSOLUTE, TEXT_DIGEST_ABSOLUTE + 20)) + [
        TIME_DISPLACEMENT_ABSOLUTE,
    ]
    for workflow in (control_dispatch, expanded_dispatch):
        require(workflow["patch"]["actual_changed_byte_offsets"] == dispatch_offsets
                and workflow["patch"]["actual_changed_byte_count"] == 2
                and workflow["patch"]["all_other_xiso_bytes_identical"] is True,
                "dispatch two-byte ledger differs")
    for workflow in (control_visible, expanded_visible):
        require(workflow["patch"]["actual_changed_byte_offsets"] == visibility_offsets
                and workflow["patch"]["actual_changed_byte_count"] == 22
                and workflow["patch"]["all_other_xiso_bytes_identical"] is True,
                "visibility 22-byte ledger differs")
    for workflow in (control_final, expanded_final):
        require(workflow["patch"]["actual_changed_byte_offsets"] == force_offsets
                and workflow["patch"]["actual_changed_byte_count"] == 21
                and workflow["patch"]["all_other_xiso_bytes_identical"] is True,
                "force-n 21-byte ledger differs")
    return workflows


def geometry_ledger(source_fd: int, geometry_fd: int, workflow: dict[str, Any]) -> None:
    before = xiso.read_exact(source_fd, GEOMETRY_ABSOLUTE, GEOMETRY_SPAN_SIZE)
    after = xiso.read_exact(geometry_fd, GEOMETRY_SPAN_OFFSET, GEOMETRY_SPAN_SIZE)
    offsets = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    before_bytes = bytes(before[index] for index in offsets)
    after_bytes = bytes(after[index] for index in offsets)
    runs: list[tuple[int, int]] = []
    for offset in offsets:
        if not runs or runs[-1][1] != offset:
            runs.append((offset, offset + 1))
        else:
            runs[-1] = (runs[-1][0], offset + 1)
    patch = workflow["patch"]
    require(
        len(offsets) == patch["changed_byte_count"] == 822_164
        and digest(before) == patch["source_span_sha256"]
        and digest(after) == patch["replacement_span_sha256"]
        and digest(before_bytes) == patch["changed_before_bytes_sha256"]
        and digest(after_bytes) == patch["changed_after_bytes_sha256"]
        and digest(b"".join(struct.pack("<I", value) for value in offsets))
        == patch["changed_offset_u32le_sha256"]
        and len(runs) == patch["changed_run_count"] == 42_649
        and digest(b"".join(struct.pack("<II", *run) for run in runs))
        == patch["changed_run_pairs_u32le_sha256"],
        "geometry replacement ledger differs",
    )


def apply(block: bytearray, position: int, offset: int, replacement: bytes) -> None:
    block_end = position + len(block)
    replacement_end = offset + len(replacement)
    start = max(position, offset)
    end = min(block_end, replacement_end)
    if start < end:
        block[start - position:end - position] = replacement[start - offset:end - offset]


def virtual_products(workflows: dict[str, dict[str, Any]], report: dict[str, Any]) -> None:
    source_fd, source_identity = open_regular(SOURCE, xiso.EXPECTED_XISO_SIZE, "retail XISO")
    geometry_fd, geometry_identity = open_regular(GEOMETRY_VOLUME, PACK9_SIZE, "geometry volume")
    try:
        entries, _directory = xiso.parse_xdvdfs(source_fd, xiso.EXPECTED_XISO_SIZE)
        files = [entry for entry in entries.values() if not (entry.attributes & 0x10)]
        pack9 = entries.get("vc_53450030/9")
        pack0 = entries.get("vc_53450030/0")
        default_xbe = entries.get("default.xbe")
        require(
            len(files) == 19 and pack9 is not None and pack0 is not None
            and default_xbe is not None
            and (pack9.byte_offset, pack9.size) == (PACK9_OFFSET, PACK9_SIZE)
            and (default_xbe.byte_offset, default_xbe.size)
            == (DEFAULT_XBE_OFFSET, DEFAULT_XBE_SIZE)
            and pack0.byte_offset <= DISPATCH_ALLOCATION
            < DISPATCH_ALLOCATION + len(ASSET_BEFORE) <= pack0.byte_offset + pack0.size,
            "retail XDVDFS target extents differ",
        )
        require(
            xiso.read_exact(source_fd, DISPATCH_ALLOCATION, len(ASSET_BEFORE)) == ASSET_BEFORE
            and xiso.read_exact(source_fd, TEXT_DIGEST_ABSOLUTE, 20) == TEXT_SOURCE_DIGEST
            and xiso.read_exact(source_fd, TIME_DISPLACEMENT_ABSOLUTE, 1) == b"\x05"
            and xiso.read_exact(source_fd, DATA_DIGEST_ABSOLUTE, 20) == DATA_SOURCE_DIGEST
            and xiso.read_exact(source_fd, UNLOCK_ABSOLUTE, 4) == UNLOCK_BEFORE,
            "retail inputs to the diagnostic patch chain differ",
        )
        geometry_ledger(source_fd, geometry_fd, workflows["expanded-wall-workflow.json"])

        retail_xbe = bytearray(xiso.read_exact(source_fd, DEFAULT_XBE_OFFSET, DEFAULT_XBE_SIZE))
        require(digest(retail_xbe) == xiso.EXPECTED_XBE_SHA256,
                "retail default.xbe identity differs")
        for offset, replacement in (
            (TEXT_DIGEST_ABSOLUTE, TEXT_OUTPUT_DIGEST),
            (TIME_DISPLACEMENT_ABSOLUTE, b"\0"),
            (DATA_DIGEST_ABSOLUTE, DATA_OUTPUT_DIGEST),
            (UNLOCK_ABSOLUTE, UNLOCK_AFTER),
        ):
            relative = offset - DEFAULT_XBE_OFFSET
            retail_xbe[relative:relative + len(replacement)] = replacement
        require(digest(retail_xbe) == FINAL_XBE_SHA256,
                "virtual final default.xbe identity differs")

        small_patches = (
            (DISPATCH_ALLOCATION, ASSET_AFTER),
            (TEXT_DIGEST_ABSOLUTE, TEXT_OUTPUT_DIGEST),
            (TIME_DISPLACEMENT_ABSOLUTE, b"\0"),
            (DATA_DIGEST_ABSOLUTE, DATA_OUTPUT_DIGEST),
            (UNLOCK_ABSOLUTE, UNLOCK_AFTER),
        )
        source_hash = hashlib.sha256()
        geometry_hash = hashlib.sha256()
        control_hash = hashlib.sha256()
        expanded_hash = hashlib.sha256()
        geometry_bytes = 0
        position = 0
        block_size = 16 * 1024 * 1024
        while position < xiso.EXPECTED_XISO_SIZE:
            source_block = os.pread(
                source_fd, min(block_size, xiso.EXPECTED_XISO_SIZE - position), position,
            )
            require(source_block, "short retail XISO read")
            source_hash.update(source_block)
            control = bytearray(source_block)
            expanded = bytearray(source_block)
            block_end = position + len(source_block)
            geometry_start = max(position, PACK9_OFFSET)
            geometry_end = min(block_end, PACK9_OFFSET + PACK9_SIZE)
            if geometry_start < geometry_end:
                replacement = os.pread(
                    geometry_fd, geometry_end - geometry_start,
                    geometry_start - PACK9_OFFSET,
                )
                require(len(replacement) == geometry_end - geometry_start,
                        "short geometry-volume read")
                geometry_hash.update(replacement)
                geometry_bytes += len(replacement)
                expanded[geometry_start - position:geometry_end - position] = replacement
            for offset, replacement in small_patches:
                apply(control, position, offset, replacement)
                apply(expanded, position, offset, replacement)
            control_hash.update(control)
            expanded_hash.update(expanded)
            position = block_end

        require(geometry_bytes == PACK9_SIZE and geometry_hash.hexdigest() == GEOMETRY_SHA256,
                "geometry-volume virtual input hash differs")
        actual = {
            "source": source_hash.hexdigest(),
            "control": control_hash.hexdigest(),
            "expanded_wall": expanded_hash.hexdigest(),
        }
        require(actual == {
            "source": SOURCE_SHA256,
            "control": CONTROL_SHA256,
            "expanded_wall": EXPANDED_SHA256,
        }, "virtual final XISO hash differs from runtime receipt")
        require(
            report["runs"]["control"]["artifacts"]["xiso"]["sha256"] == actual["control"]
            and report["runs"]["expanded_wall"]["artifacts"]["xiso"]["sha256"]
            == actual["expanded_wall"],
            "runtime selected-XISO receipt differs from virtual products",
        )
    finally:
        close_unchanged(SOURCE, source_fd, source_identity, "retail XISO")
        close_unchanged(
            GEOMETRY_VOLUME, geometry_fd, geometry_identity, "geometry volume",
        )


def validate_chain(path: Path, leaf: str) -> None:
    chain = json.loads(path.read_bytes())
    expected = [
        leaf, "group36_selection_seed", "group36_root", "scorebug_runtime",
        "away_cacheclear", "jersey_tset_controller_base",
    ]
    require(
        chain["schema"] == "nfl2k5_historical_xemu_hdd_chain_verify/v1"
        and chain["leaf"] == leaf and chain["base_status"] == "missing"
        and chain["chain_complete"] is False
        and chain["guest_content_replayable"] is False
        and chain["historical_runtime_reexecuted"] is False
        and chain["missing_base_reconstructed"] is False
        and chain["substitution_allowed"] is False
        and [row["id"] for row in chain["layers"]] == expected
        and chain["layers"][-1]["pin"] is None,
        f"{leaf} retained QCOW2 causal boundary differs",
    )


def validate_configs(report: dict[str, Any]) -> None:
    for name in ("control", "expanded_wall"):
        artifacts = report["runs"][name]["artifacts"]
        text = resolve_record(artifacts["config"]).read_text(encoding="utf-8")
        expected_hdd = str(resolve_record(artifacts["hdd"]).resolve())
        expected_xiso = str(resolve_record(artifacts["xiso"]).resolve())
        require(f"hdd_path = '{expected_hdd}'" in text,
                f"{name} retained config HDD selection differs")
        require(f"dvd_path = '{expected_xiso}'" in text,
                f"{name} retained config DVD selection differs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-chain", type=Path, required=True)
    parser.add_argument("--expanded-chain", type=Path, required=True)
    args = parser.parse_args()
    report = read_pinned_json(REPORT, REPORT_PIN, "runtime report")
    require(report["schema"] == "nfl2k5_group36_xemu_runtime_result/v2"
            and report["status"] == "pinned_xemu_diagnostic_geometry_visible",
            "runtime report identity differs")
    pin_retained_report_artifacts(report)
    validate_claim_boundary(report)
    validate_configs(report)
    workflows = validate_workflows(report)
    virtual_products(workflows, report)
    validate_chain(args.control_chain, "group36_control_matched")
    validate_chain(args.expanded_chain, "group36_expanded")
    print(
        "NFL_GROUP36_RUNTIME_RECEIPT_VERIFY_PASS virtual_xisos=2 exact_hashes=true "
        "retained_artifacts=true screenshots=4 configs=2 hdd_leaves=2 "
        "geometry_visible=pinned_receipt pixel_aligned=false chain_complete=false "
        "guest_content_replayable=false historical_runtime_reexecuted=false "
        "emulator_started=false output_xiso_written=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ReceiptError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
