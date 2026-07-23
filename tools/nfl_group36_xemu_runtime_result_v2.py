#!/usr/bin/env python3
"""Validate the pinned positive NFL 2K5 group36 xemu diagnostic result.

This is a read-only evidence validator.  It does not launch xemu, inspect
pixels, or infer a general mesh-writer claim.  The positive geometry result is
deliberately bounded to one exact control/expanded pair, one deterministic
replay-camera sequence, and one independently verified authored group36
payload.  The earlier v1 selector-negative result remains a separate frozen
artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ID = "nfl2k5_group36_xemu_runtime_result/v2"
SCHEMA_URI = "urn:nfl2k5-group36-xemu-runtime-result:v2"
SCHEMA_PATH = ROOT / "reports/specs/nfl2k5_group36_xemu_runtime_result.v2.schema.json"
SCHEMA_SIZE = 15_865
SCHEMA_SHA256 = "bd580e1abd911f5dbe16f733ececc843f94f2e862f233db10b766f38cec1c370"
MAX_JSON_BYTES = 512 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

RUN_NAMES = ("control", "expanded_wall")
SCREENSHOT_ROLES = ("geometry_frame", "target_selection")

EMULATOR = {
    "application": "app.xemu.xemu",
    "commit": "6318bb112091635ef908255019e4d42956bc5fa8",
    "renderer": "llvmpipe / LLVM 21.1.8 / Mesa 26.1.4",
    "version": "0.8.135",
}

SELECTION = {
    "actual_asset_code": "s42",
    "roster_record_index": 18,
    "time_of_day": "Night",
    "visible_label": "Giants Stadium",
    "weather": "Clear",
}

TARGET = {
    "actual_asset_code": "s42",
    "outer_filename": "s42nd.iff",
    "outer_id": "0xe4d6b0bc",
    "outer_index": 3280,
    "roster_record_index": 18,
    "stadium_family": "Super Bowl 2006 Stadium / Ford Field",
    "time_of_day": "Night",
    "visible_label": "Giants Stadium",
    "weather": "Clear",
}

CAMERA_PROTOCOL = {
    "comparison_limitation": (
        "same replay route and end-zone-facing sequence, but not pixel-aligned "
        "because play and team state differ"
    ),
    "end_zone_facing": True,
    "pixel_aligned": False,
    "same_play_state": False,
    "same_sequence": True,
    "same_team_state": False,
    "steps": [
        {
            "duration_seconds": "4.00",
            "gap_seconds": None,
            "input": "left_stick_down",
            "press_seconds": None,
            "tap_count": None,
        },
        {
            "duration_seconds": None,
            "gap_seconds": "0.05",
            "input": "dpad_up",
            "press_seconds": "0.06",
            "tap_count": 15,
        },
        {
            "duration_seconds": None,
            "gap_seconds": "0.04",
            "input": "button_b_zoom_out",
            "press_seconds": "0.05",
            "tap_count": 30,
        },
    ],
}

DIAGNOSTIC_LAYERS = [
    "record18 ROST asset-code dispatch s18 to s42",
    "s42 Quick Game availability unlock id 0x014b to zero",
    "global stadium filename time suffix forced to n",
    (
        "expanded profile only: independently verified group36 same-footprint "
        "authored wall payload"
    ),
]

PAIR = {
    "camera_protocol": CAMERA_PROTOCOL,
    "diagnostic_layers": DIAGNOSTIC_LAYERS,
    "id": "nfl2k5_group36_s42_visible_night_control_expanded/v2",
    "target": TARGET,
}

EXPANDED_PAYLOAD = {
    "decoded_changed_byte_count": 48,
    "degenerate_triangle_count": 0,
    "fixed_tail_exact": True,
    "independent_verifier_passed": True,
    "nondegenerate_triangle_count": 2,
    "outer_id": "0xe4d6b0bc",
    "outer_index": 3280,
    "outside_authorized_geometry_bit_exact": True,
    "outside_target_chunk_bit_exact": True,
    "shape_name": "group36",
}

OFFLINE_ARTIFACTS = {
    "archive_index": {
        "path": "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0",
        "sha256": "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
        "size": 193_710_080,
    },
    "expanded_geometry_manifest": {
        "path": ".geometry-proof/expanded-wall-output/manifest.json",
        "sha256": "8d5454101129b8fc626cb42ac238ca49c6b39a4c0bdd52649fb1eba0a62d6417",
        "size": 4_319,
    },
    "expanded_geometry_volume": {
        "path": ".geometry-proof/expanded-wall-output/9",
        "sha256": "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad",
        "size": 634_941_440,
    },
    "expanded_recipe": {
        "path": (
            ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/"
            "expanded_local_wall_recipe.json"
        ),
        "sha256": "3ee45f7b36fae28e51814e7695dc9bbd20d3ea4ac3a722ca53e9bf1264639625",
        "size": 1_824,
    },
    "force_n_spec": {
        "path": "reports/specs/nfl2k5_group36_s42_force_n_runtime_shim.v1.json",
        "sha256": "92f7dcc820cc4b6d4e8049737a2aa4a9d4b228e09531f22e34d48cd5c7576048",
        "size": 7_792,
    },
    "independent_verifier": {
        "path": "tools/nfl_stadium_group36_geometry_verify.py",
        "sha256": "3b14f95c73d64def0a352ea09c106c4ecbc43eea79b5ae59cb4bb72f2db6f1e6",
        "size": 25_899,
    },
    "visibility_unlock_spec": {
        "path": (
            "reports/specs/"
            "nfl2k5_stadium_quick_game_visibility_and_s42_unlock_diagnostic.v1.json"
        ),
        "sha256": "7078157b445a745328a5057a5ec74135c8e69b06afda982c49ee20fc3a7d8478",
        "size": 9_888,
    },
}

RUNS = {
    "control": {
        "artifacts": {
            "config": {
                "path": (
                    ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/"
                    "xemu-s42-visible-night-control-matched.toml"
                ),
                "sha256": "cb9adf45b653f976c7dcb2911e4ea285d2672c6aee2d249787af6c2a0a793bb8",
                "size": 954,
            },
            "hdd": {
                "path": (
                    ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/"
                    "xbox_hdd-s42-visible-night-control-matched.qcow2"
                ),
                "sha256": "29cc4518d077d15d605fa3668c109286867737c529044e0b9fb52c343a12a5ef",
                "size": 7_012_352,
            },
            "screenshots": [
                {
                    "path": (
                        ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/"
                        "logs/control-s42nd-replay-matched.png"
                    ),
                    "role": "geometry_frame",
                    "sha256": (
                        "201b4d68bd105f9548892254a62ab4e48162b25b6d548ef78972252698a9ba79"
                    ),
                    "size": 602_224,
                },
                {
                    "path": (
                        ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/"
                        "logs/control-visible-night-s42-selection.png"
                    ),
                    "role": "target_selection",
                    "sha256": (
                        "da83ed4cb0ebc98c50e22b98ad264f742e86ab7235864145725797980571d1a4"
                    ),
                    "size": 292_537,
                },
            ],
            "workflow_manifest": {
                "path": (
                    "build/nfl2k5-stadium-group36-geometry-xiso-20260713/"
                    "s42-visible-night-control-workflow.json"
                ),
                "sha256": "cb503cc117909eb78048dc96f68a1b1ccd12c6223781eba6742e6a0c12cff5db",
                "size": 7_227,
            },
            "xiso": {
                "path": (
                    "build/nfl2k5-stadium-group36-geometry-xiso-20260713/"
                    "ESPN-NFL-2K5-s42-visible-night-control.xiso.iso"
                ),
                "sha256": "863ba00df855efdf54b85d568516b1ed0f7bbd33ddb77096ce3e16da4e702383",
                "size": 6_300_499_968,
            },
        },
        "profile": "retail_geometry_diagnostic_control",
        "runtime": {
            "authored_wall_visible": False,
            "clean_shutdown_observed": True,
            "exit_code": 0,
            "hdd_qemu_img_check": "no errors",
            "render_observation": (
                "Ford Field / Super Bowl XL environment rendered; no giant authored wall "
                "is present in the end-zone-facing replay frame."
            ),
            "selection": SELECTION,
            "shutdown_method": "WM_DELETE_WINDOW",
            "target_outer_derivation": (
                "record18 asset s42 + forced time suffix n + clear weather suffix d "
                "=> s42nd.iff"
            ),
        },
    },
    "expanded_wall": {
        "artifacts": {
            "config": {
                "path": (
                    ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/"
                    "xemu-s42-visible-night-expanded.toml"
                ),
                "sha256": "db12d27d37e5fa30b5ae4d0d425537cfda2407f9d87d8bc832472d39e1fe72f2",
                "size": 961,
            },
            "hdd": {
                "path": (
                    ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/"
                    "xbox_hdd-s42-visible-night-expanded.qcow2"
                ),
                "sha256": "f43edbf83f16ff6d233dfb712963ca68554a77020ffd63b2cabe5d049cef1dc2",
                "size": 5_439_488,
            },
            "screenshots": [
                {
                    "path": (
                        ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/"
                        "logs/expanded-replay-zoomout30.png"
                    ),
                    "role": "geometry_frame",
                    "sha256": (
                        "e67bf8627b0c3c7135d62143669ac6c94e2204973283971c967b0f46fb646f07"
                    ),
                    "size": 587_300,
                },
                {
                    "path": (
                        ".codex-tmp/nfl2k5-group36-geometry-xemu-20260713/"
                        "logs/expanded-visible-night-s42-selection.png"
                    ),
                    "role": "target_selection",
                    "sha256": (
                        "3ee63e160ee7a6be2dc4ac158c1b4c37ed03c75eeaa43c95fea939b84e3a10ce"
                    ),
                    "size": 294_122,
                },
            ],
            "workflow_manifest": {
                "path": (
                    "build/nfl2k5-stadium-group36-geometry-xiso-20260713/"
                    "expanded-wall-s42-visible-night-workflow.json"
                ),
                "sha256": "a003d7f04e23c291e28c577923d332080f74bca8a749881972325a82f285a97b",
                "size": 7_287,
            },
            "xiso": {
                "path": (
                    "build/nfl2k5-stadium-group36-geometry-xiso-20260713/"
                    "ESPN-NFL-2K5-group36-expanded-wall-s42-visible-night.xiso.iso"
                ),
                "sha256": "d41c44882919a00282c184fcc85b4ec139e17b48ee7681960808cc14947bab72",
                "size": 6_300_499_968,
            },
        },
        "profile": "expanded_wall_diagnostic",
        "runtime": {
            "authored_wall_visible": True,
            "clean_shutdown_observed": True,
            "exit_code": 0,
            "hdd_qemu_img_check": "no errors",
            "render_observation": (
                "Ford Field / Super Bowl XL environment rendered; a giant dark authored "
                "wall spans the left/center field of the end-zone-facing replay frame."
            ),
            "selection": SELECTION,
            "shutdown_method": "WM_DELETE_WINDOW",
            "target_outer_derivation": (
                "record18 asset s42 + forced time suffix n + clear weather suffix d "
                "=> s42nd.iff"
            ),
        },
    },
}

PROOF_BOUNDARY = {
    "comparison_standard": (
        "uniquely authored diagnostic geometry plus independently verified payload and "
        "repeated deterministic camera sequence"
    ),
    "geometry_visibility_scope": (
        "the exact pinned group36 expanded-wall payload visibly affects rendering in "
        "xemu 0.8.135 for s42nd.iff"
    ),
    "not_proved": [
        "pixel-aligned same-play and same-team matched frames",
        "runtime resource-loader or GPU draw trace",
        "general static-mesh runtime write-back beyond this four-vertex same-footprint profile",
        (
            "changed-count, relocation, material, UV, normal, skin, morph, bounds, or "
            "decimation write-back"
        ),
        "original Xbox hardware acceptance",
        "retail RSA signed executable chain preservation",
        "production, distribution, or public-editor readiness",
    ],
    "positive_derivation": [
        (
            "both exact diagnostic XISOs reached the selected game and exited xemu with "
            "code zero through WM_DELETE_WINDOW"
        ),
        (
            "both runs used the same deterministic replay and end-zone-facing "
            "camera-input sequence"
        ),
        "the expanded frame visibly contains a giant dark wall absent from the control frame",
        (
            "the wall is uniquely attributable to the expanded profile's authored "
            "four-vertex group36 payload"
        ),
        (
            "the writer-independent verifier proves 48 changed decoded bytes, two "
            "nondegenerate triangles, exact fixed tail, and exact bytes outside the "
            "authorized geometry"
        ),
    ],
    "target_load_derivation": [
        (
            "the pinned dispatch layer changes roster record18's loader asset code from "
            "s18 to s42 while retaining its Giants Stadium label and preview identity"
        ),
        (
            "the pinned unlock layer makes that exact s42 record selectable, and both "
            "target-selection captures show record18 with Night and Clear"
        ),
        (
            "the pinned filename dataflow forces time suffix n while Clear supplies "
            "weather suffix d"
        ),
        (
            "the executable's percent-s-percent-c-percent-c-dot-iff construction therefore "
            "resolves the active record to s42nd.iff"
        ),
        (
            "the static archive identity maps s42nd.iff to outer 0xe4d6b0bc at index 3280"
        ),
        (
            "both runs render the Ford Field and Super Bowl XL stadium family, "
            "independently corroborating the s42 route"
        ),
    ],
}

CLAIM_KEYS = {
    "changed_count_mesh_writeback_proved",
    "control_target_outer_loaded_proved",
    "diagnostic_only",
    "distribution_ready",
    "expanded_target_outer_loaded_proved",
    "general_static_mesh_runtime_writeback_proved",
    "geometry_visibility_proved",
    "geometry_visibility_scope_pinned_xemu_diagnostic_only",
    "original_xbox_hardware_proved",
    "pixel_aligned_matched_pair_proved",
    "production_ready",
    "public_editor_exposed",
    "retail_signed_executable_chain_preserved",
    "runtime_gpu_trace_proved",
    "s42_quick_game_selectability_proved",
    "same_camera_sequence_proved",
    "strict_v1_exact_frame_branch_satisfied",
    "target_outer_loaded_proved",
    "xemu_boot_acceptance_proved",
    "xemu_clean_shutdown_pair_observed",
}


class ResultError(ValueError):
    """Schema, identity, evidence, or claim-boundary failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ResultError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(8 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ResultError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_canonical_json(path: Path, *, maximum: int = MAX_JSON_BYTES) -> dict[str, Any]:
    raw = path.read_bytes()
    require(0 < len(raw) <= maximum, f"{path} size is outside the bounded JSON range")

    def reject_constant(value: str) -> None:
        raise ResultError(f"non-JSON numeric constant in {path}: {value}")

    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ResultError(f"invalid JSON in {path}: {exc}") from exc
    require(isinstance(value, dict), f"{path} top level must be an object")
    canonical = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    require(raw == canonical, f"{path} must be canonical sorted UTF-8 JSON")
    return value


def validate_schema_identity() -> None:
    require(SCHEMA_PATH.is_file() and not SCHEMA_PATH.is_symlink(),
            "v2 schema is absent or a symlink")
    require(SCHEMA_PATH.stat().st_size == SCHEMA_SIZE, "v2 schema size identity drift")
    require(sha256_file(SCHEMA_PATH) == SCHEMA_SHA256, "v2 schema SHA-256 identity drift")
    schema = load_canonical_json(SCHEMA_PATH)
    require(schema.get("$id") == SCHEMA_URI, "v2 schema URI drift")
    claims = schema["properties"]["claims"]["properties"]
    for key in (
        "distribution_ready",
        "original_xbox_hardware_proved",
        "production_ready",
        "public_editor_exposed",
        "retail_signed_executable_chain_preserved",
    ):
        require(claims[key] == {"const": False}, f"v2 schema no longer const-falses {key}")


def _exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == keys, f"{label} key set differs")
    return value


def _safe_relative_path(value: Any, label: str) -> str:
    require(isinstance(value, str) and value and "\x00" not in value,
            f"{label} path is invalid")
    path = PurePosixPath(value)
    require(not path.is_absolute(), f"{label} path must be workspace-relative")
    require(".." not in path.parts and str(path) == value, f"{label} path is noncanonical")
    return value


def _artifact(value: Any, label: str) -> dict[str, Any]:
    row = _exact_keys(value, {"path", "sha256", "size"}, label)
    _safe_relative_path(row["path"], label)
    require(type(row["size"]) is int and row["size"] > 0, f"{label} size is invalid")
    require(isinstance(row["sha256"], str) and SHA256_RE.fullmatch(row["sha256"]),
            f"{label} SHA-256 is invalid")
    return row


def _screenshot(value: Any, label: str) -> dict[str, Any]:
    row = _exact_keys(value, {"path", "role", "sha256", "size"}, label)
    _safe_relative_path(row["path"], label)
    require(row["role"] in SCREENSHOT_ROLES, f"{label} role is invalid")
    require(type(row["size"]) is int and row["size"] > 0, f"{label} size is invalid")
    require(isinstance(row["sha256"], str) and SHA256_RE.fullmatch(row["sha256"]),
            f"{label} SHA-256 is invalid")
    return row


def _verify_file(root: Path, row: dict[str, Any], label: str) -> Path:
    path = root / row["path"]
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ResultError(f"{label} cannot be stated: {exc}") from exc
    require(stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode),
            f"{label} is not a non-symlink regular file")
    require(metadata.st_size == row["size"], f"{label} size differs")
    require(sha256_file(path) == row["sha256"], f"{label} SHA-256 differs")
    return path


def _verify_png(
    path: Path,
    label: str,
    expected_dimensions: tuple[int, int] = (1280, 720),
) -> None:
    with path.open("rb") as handle:
        header = handle.read(24)
    require(len(header) == 24 and header[:8] == b"\x89PNG\r\n\x1a\n",
            f"{label} is not a PNG")
    require(header[12:16] == b"IHDR", f"{label} lacks a leading IHDR")
    width, height = struct.unpack(">II", header[16:24])
    require((width, height) == expected_dimensions, f"{label} dimensions differ")


def _target_loaded(run: dict[str, Any]) -> bool:
    artifacts = run["artifacts"]
    roles = {row["role"] for row in artifacts["screenshots"]}
    runtime = run["runtime"]
    return (
        roles == set(SCREENSHOT_ROLES)
        and runtime["selection"] == SELECTION
        and runtime["target_outer_derivation"]
        == "record18 asset s42 + forced time suffix n + clear weather suffix d => s42nd.iff"
        and runtime["clean_shutdown_observed"] is True
        and runtime["exit_code"] == 0
        and "Ford Field / Super Bowl XL environment rendered" in runtime["render_observation"]
    )


def derive_claims(document: dict[str, Any]) -> dict[str, bool]:
    runs = document["runs"]
    control_loaded = _target_loaded(runs["control"])
    expanded_loaded = _target_loaded(runs["expanded_wall"])
    camera = document["pair"]["camera_protocol"]
    same_sequence = (
        camera.get("same_sequence") is True
        and camera.get("end_zone_facing") is True
        and camera.get("steps") == CAMERA_PROTOCOL["steps"]
    )
    clean_pair = all(
        runs[name]["runtime"].get("exit_code") == 0
        and runs[name]["runtime"].get("clean_shutdown_observed") is True
        and runs[name]["runtime"].get("shutdown_method") == "WM_DELETE_WINDOW"
        for name in RUN_NAMES
    )
    payload = document["offline_proof"]["expanded_payload"]
    wall_attributed = (
        runs["control"]["runtime"].get("authored_wall_visible") is False
        and runs["expanded_wall"]["runtime"].get("authored_wall_visible") is True
        and payload == EXPANDED_PAYLOAD
    )
    geometry = control_loaded and expanded_loaded and same_sequence and wall_attributed
    pixel_aligned = (
        camera.get("pixel_aligned") is True
        and camera.get("same_play_state") is True
        and camera.get("same_team_state") is True
    )
    return {
        "changed_count_mesh_writeback_proved": False,
        "control_target_outer_loaded_proved": control_loaded,
        "diagnostic_only": True,
        "distribution_ready": False,
        "expanded_target_outer_loaded_proved": expanded_loaded,
        "general_static_mesh_runtime_writeback_proved": False,
        "geometry_visibility_proved": geometry,
        "geometry_visibility_scope_pinned_xemu_diagnostic_only": geometry,
        "original_xbox_hardware_proved": False,
        "pixel_aligned_matched_pair_proved": pixel_aligned,
        "production_ready": False,
        "public_editor_exposed": False,
        "retail_signed_executable_chain_preserved": False,
        "runtime_gpu_trace_proved": False,
        "s42_quick_game_selectability_proved": control_loaded and expanded_loaded,
        "same_camera_sequence_proved": same_sequence,
        "strict_v1_exact_frame_branch_satisfied": pixel_aligned,
        "target_outer_loaded_proved": control_loaded and expanded_loaded,
        "xemu_boot_acceptance_proved": control_loaded and expanded_loaded,
        "xemu_clean_shutdown_pair_observed": clean_pair,
    }


def derive_status(claims: dict[str, bool]) -> str:
    if claims["geometry_visibility_proved"]:
        return "pinned_xemu_diagnostic_geometry_visible"
    if claims["target_outer_loaded_proved"]:
        return "pinned_xemu_diagnostic_target_loaded"
    if claims["xemu_boot_acceptance_proved"]:
        return "pinned_xemu_diagnostic_booted"
    return "unproved"


def _validate_run(name: str, run: Any) -> None:
    expected = RUNS[name]
    row = _exact_keys(run, {"artifacts", "profile", "runtime"}, f"runs.{name}")
    require(row["profile"] == expected["profile"], f"runs.{name} profile differs")
    artifacts = _exact_keys(
        row["artifacts"],
        {"config", "hdd", "screenshots", "workflow_manifest", "xiso"},
        f"runs.{name}.artifacts",
    )
    for key in ("config", "hdd", "workflow_manifest", "xiso"):
        value = _artifact(artifacts[key], f"runs.{name}.{key}")
        require(value == expected["artifacts"][key], f"runs.{name}.{key} identity differs")
    screenshots = artifacts["screenshots"]
    require(isinstance(screenshots, list) and len(screenshots) == 2,
            f"runs.{name}.screenshots must contain exactly two rows")
    validated = [
        _screenshot(value, f"runs.{name}.screenshots[{index}]")
        for index, value in enumerate(screenshots)
    ]
    require([row["role"] for row in validated] == list(SCREENSHOT_ROLES),
            f"runs.{name}.screenshots must be unique and canonical-role ordered")
    require(validated == expected["artifacts"]["screenshots"],
            f"runs.{name}.screenshots identities differ")
    runtime = _exact_keys(
        row["runtime"],
        {
            "authored_wall_visible",
            "clean_shutdown_observed",
            "exit_code",
            "hdd_qemu_img_check",
            "render_observation",
            "selection",
            "shutdown_method",
            "target_outer_derivation",
        },
        f"runs.{name}.runtime",
    )
    require(runtime == expected["runtime"], f"runs.{name}.runtime observation differs")


def _verify_workflow_semantics(root: Path, name: str) -> None:
    expected = RUNS[name]["artifacts"]
    workflow = load_canonical_json(root / expected["workflow_manifest"]["path"])
    profile = "s42_control" if name == "control" else "s42_expanded_wall"
    pack9 = (
        "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a"
        if name == "control"
        else "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad"
    )
    require(workflow.get("schema") == "nfl2k5_group36_s42_force_n_xiso_patch/v1",
            f"{name} workflow schema differs")
    require(workflow.get("source_profile") == profile, f"{name} workflow profile differs")
    require(workflow.get("output", {}).get("sha256") == expected["xiso"]["sha256"]
            and workflow.get("output", {}).get("size") == expected["xiso"]["size"],
            f"{name} workflow output identity differs")
    require(workflow.get("xdvdfs", {}).get("pack9_sha256") == pack9,
            f"{name} workflow volume9 identity differs")
    require(workflow.get("xbe", {}).get("dataflow", {}).get("s42_clear_result") == "s42nd.iff",
            f"{name} workflow target filename differs")
    require(workflow.get("xbe", {}).get("output", {}).get("xbe_sha256")
            == "c6abdd77be89594ee19dbfd8dbfa300b592a5a2ed1af2276e5e132678e50cc27",
            f"{name} workflow XBE identity differs")
    claims = workflow.get("claims", {})
    require(claims.get("diagnostic_only") is True, f"{name} workflow is not diagnostic")
    for key in (
        "original_xbox_hardware_proved",
        "production_ready",
        "public_editor_exposed",
        "retail_signed_executable_chain_preserved",
    ):
        require(claims.get(key) is False, f"{name} workflow overclaims {key}")


def _verify_offline_semantics(root: Path) -> None:
    manifest = load_canonical_json(
        root / OFFLINE_ARTIFACTS["expanded_geometry_manifest"]["path"]
    )
    require(manifest.get("schema") == "nfl2k5_group36_same_footprint_geometry_patch/v1",
            "expanded geometry manifest schema differs")
    require(manifest.get("mode") == "patched", "expanded geometry manifest is not patched")
    require(manifest.get("output", {}).get("volume_sha256")
            == OFFLINE_ARTIFACTS["expanded_geometry_volume"]["sha256"],
            "expanded geometry volume identity differs from its manifest")
    require(manifest.get("edit", {}).get("decoded_changed_byte_count") == 48,
            "expanded decoded changed-byte count differs")
    require(manifest.get("edit", {}).get("every_decoded_byte_outside_authorized_spans_bit_exact")
            is True, "expanded bytes outside authorized spans are not exact")
    require(manifest.get("output", {}).get("outside_target_chunk_bit_exact") is True,
            "expanded bytes outside target chunk are not exact")
    require(manifest.get("compression", {}).get("fixed_opaque_tail_sha256")
            == "cb57e42b9b8d9e1cba31e18c38dbc3347c8caa1361fcf7fe9cfad5b9f138fae4",
            "expanded fixed tail identity differs")
    target = manifest.get("target", {})
    require(
        {
            "outer_id": target.get("outer_id"),
            "outer_index": target.get("outer_index"),
            "shape_name": target.get("shape_name"),
        }
        == {"outer_id": "0xe4d6b0bc", "outer_index": 3280, "shape_name": "group36"},
        "expanded geometry target differs",
    )

    recipe = load_canonical_json(root / OFFLINE_ARTIFACTS["expanded_recipe"]["path"])
    require(recipe.get("operation")
            == "replace_exact_same_footprint_positions_and_quad_indices",
            "expanded recipe operation differs")
    require(recipe.get("indices") == [0, 2, 1, 3], "expanded recipe index order differs")
    positions = recipe.get("positions")
    require(isinstance(positions, list) and len(positions) == 4,
            "expanded recipe must contain four positions")
    require(all(
        isinstance(position, list)
        and len(position) == 3
        and all(type(component) in (int, float) and math.isfinite(component)
                for component in position)
        for position in positions
    ), "expanded recipe positions are invalid")
    require(recipe.get("target", {}).get("outer_id") == "0xe4d6b0bc"
            and recipe.get("target", {}).get("outer_index") == 3280
            and recipe.get("target", {}).get("shape_name") == "group36",
            "expanded recipe target differs")

    force_n = load_canonical_json(root / OFFLINE_ARTIFACTS["force_n_spec"]["path"])
    require(force_n.get("schema") == "nfl2k5_group36_s42_force_n_runtime_shim/v1",
            "force-n spec schema differs")
    require(force_n.get("claims", {}).get("offline_force_n_dataflow_proved") is True,
            "force-n dataflow is not offline-proved")
    require(force_n.get("dataflow", {}).get("format") == "%s%c%c.iff"
            and force_n.get("runtime_contract", {}).get("expected_outer_names", {}).get("clear")
            == "s42nd.iff", "force-n target construction differs")
    require(force_n.get("claims", {}).get("retail_signed_executable_chain_preserved") is False,
            "force-n spec unexpectedly preserves the signed chain")

    visibility = load_canonical_json(
        root / OFFLINE_ARTIFACTS["visibility_unlock_spec"]["path"]
    )
    require(visibility.get("schema")
            == "nfl2k5_stadium_quick_game_visibility_and_s42_unlock_diagnostic/v1",
            "visibility-unlock spec schema differs")
    require(visibility.get("claims", {}).get("offline_zero_unlock_id_path_proved") is True,
            "s42 zero-unlock visibility path is not offline-proved")
    require(visibility.get("rost_stadium_format", {}).get("record18", {}).get(
        "asset_code_after_dispatch_shim") == "s42",
        "record18 loader asset code differs",
    )


def _verify_config_semantics(root: Path, name: str) -> None:
    artifacts = RUNS[name]["artifacts"]
    text = (root / artifacts["config"]["path"]).read_text(encoding="utf-8")
    expected_hdd = str((root / artifacts["hdd"]["path"]).resolve())
    expected_xiso = str((root / artifacts["xiso"]["path"]).resolve())
    require(f"hdd_path = '{expected_hdd}'" in text, f"{name} config HDD path differs")
    require(f"dvd_path = '{expected_xiso}'" in text, f"{name} config XISO path differs")


def _verify_all_files(root: Path, document: dict[str, Any]) -> None:
    seen: set[str] = set()
    for key in sorted(OFFLINE_ARTIFACTS):
        row = document["offline_proof"][key]
        require(row["path"] not in seen, "duplicate evidence path")
        seen.add(row["path"])
        _verify_file(root, row, f"offline_proof.{key}")
    for name in RUN_NAMES:
        artifacts = document["runs"][name]["artifacts"]
        for key in ("config", "hdd", "workflow_manifest", "xiso"):
            row = artifacts[key]
            require(row["path"] not in seen, "duplicate evidence path")
            seen.add(row["path"])
            _verify_file(root, row, f"runs.{name}.{key}")
        for index, row in enumerate(artifacts["screenshots"]):
            require(row["path"] not in seen, "duplicate evidence path")
            seen.add(row["path"])
            path = _verify_file(root, row, f"runs.{name}.screenshots[{index}]")
            expected_dimensions = (
                (1280, 672) if row["role"] == "geometry_frame" else (1280, 720)
            )
            _verify_png(
                path,
                f"runs.{name}.screenshots[{index}]",
                expected_dimensions,
            )
        _verify_config_semantics(root, name)
        _verify_workflow_semantics(root, name)
    _verify_offline_semantics(root)


def validate_document(
    document: dict[str, Any],
    *,
    verify_files: bool = False,
    root: Path = ROOT,
) -> dict[str, bool]:
    _exact_keys(
        document,
        {"claims", "date", "emulator", "offline_proof", "pair", "proof_boundary",
         "runs", "schema", "status"},
        "result",
    )
    require(document["schema"] == SCHEMA_ID, "result schema differs")
    require(document["date"] == "2026-07-13", "result date differs")
    require(document["emulator"] == EMULATOR, "emulator identity differs")
    require(document["pair"] == PAIR, "paired target or camera contract differs")
    require(document["proof_boundary"] == PROOF_BOUNDARY, "proof boundary differs")

    offline = _exact_keys(
        document["offline_proof"],
        set(OFFLINE_ARTIFACTS) | {"expanded_payload"},
        "offline_proof",
    )
    require(offline["expanded_payload"] == EXPANDED_PAYLOAD,
            "offline expanded payload proof differs")
    for key, expected in OFFLINE_ARTIFACTS.items():
        row = _artifact(offline[key], f"offline_proof.{key}")
        require(row == expected, f"offline_proof.{key} identity differs")

    runs = _exact_keys(document["runs"], set(RUN_NAMES), "runs")
    for name in RUN_NAMES:
        _validate_run(name, runs[name])

    claims = _exact_keys(document["claims"], CLAIM_KEYS, "claims")
    require(all(type(value) is bool for value in claims.values()),
            "claims must all be booleans")
    derived = derive_claims(document)
    require(claims == derived, "claims do not equal independently derived evidence")
    require(document["status"] == derive_status(derived),
            "status does not equal independently derived evidence")

    require(derived["geometry_visibility_proved"] is True,
            "pinned diagnostic geometry visibility is not proved")
    require(derived["pixel_aligned_matched_pair_proved"] is False,
            "the non-pixel-aligned frames cannot become a matched-frame claim")
    require(derived["strict_v1_exact_frame_branch_satisfied"] is False,
            "the v1 exact-frame branch cannot be claimed")
    for key in (
        "distribution_ready",
        "original_xbox_hardware_proved",
        "production_ready",
        "public_editor_exposed",
        "retail_signed_executable_chain_preserved",
    ):
        require(derived[key] is False, f"forbidden positive claim: {key}")

    if verify_files:
        _verify_all_files(root, document)
    return derived


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--verify-files", action="store_true")
    args = parser.parse_args()
    try:
        validate_schema_identity()
        document = load_canonical_json(args.result)
        claims = validate_document(document, verify_files=args.verify_files, root=args.root)
    except (OSError, ResultError) as exc:
        print(f"NFL_GROUP36_XEMU_RUNTIME_RESULT_V2_REFUSED reason={exc}", file=sys.stderr)
        return 2
    print(
        "NFL_GROUP36_XEMU_RUNTIME_RESULT_V2_PASS"
        f" status={document['status']}"
        f" target_loaded={str(claims['target_outer_loaded_proved']).lower()}"
        f" geometry_visible={str(claims['geometry_visibility_proved']).lower()}"
        f" same_sequence={str(claims['same_camera_sequence_proved']).lower()}"
        " pixel_aligned=false gpu_trace=false hardware=false rsa_chain=false"
        " distribution=false production=false public_editor=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
