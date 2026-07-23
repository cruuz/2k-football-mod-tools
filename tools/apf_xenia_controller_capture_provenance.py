#!/usr/bin/env python3
"""Validate frozen controller bytes for the three legacy APF Xenia captures."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "reports/assets/apf_xenia_controller_capture_provenance.v1.json"
MANIFEST_SIZE = 4304
MANIFEST_SHA256 = "c4fd63b6d831637a2904396e106282103d3f923c16cab58066d7f68337b97120"
RECORDED_INVOCATION_PATH = "tools/xenia_virtual_gamepad.py"
FROZEN_SOURCE = (
    "reports/cut_content/apf_nfl_lineage/runtime_provenance/"
    "xenia_virtual_gamepad."
    "fe63265a8e19a873adb794be132f84a44b7a40cd488d753505751470fdaf48dc.py"
)
FROZEN_SOURCE_SIZE = 3051
FROZEN_SOURCE_SHA256 = (
    "fe63265a8e19a873adb794be132f84a44b7a40cd488d753505751470fdaf48dc"
)

EXPECTED_RECOVERY = {
    "method": (
        "byte-exact recovery from a later preserved session output that printed "
        "the then-current controller helper; accepted because its length and "
        "digest matched the capture-time hashes in all three legacy "
        "report/transcript pairs"
    ),
    "session_log_home_relative": (
        ".codex/sessions/2026/07/15/"
        "rollout-2026-07-15T19-12-41-019f680d-c783-7bd3-bd51-a51e3362cf38.jsonl"
    ),
    "session_output_line": 1019,
    "session_output_timestamp_utc": "2026-07-16T00:28:00.057Z",
    "session_output_call_id": "call_TZOE0bBBRsj56i82FpUuYPNS",
    "listing_postdates_capture": True,
    "listing_is_original_capture_session": False,
    "recovered_bytes_are_authority": False,
    "frozen_repository_copy_is_authority": True,
}

EXPECTED_BINDINGS = [
    {
        "id": "americans_uniform_solid_20260710",
        "report": {
            "path": "reports/assets/apf_uniform_xenia_runtime.json",
            "size_bytes": 9287,
            "sha256": (
                "0eabe929101c08d7e83b36ed6ef12e61e18703d3d7bbdb6808650a1181d021bf"
            ),
            "schema": "apf_uniform_xenia_runtime/v1",
            "transcript_path_field": "control_input_transcript",
            "transcript_sha256_field": "control_input_transcript_sha256",
            "transcript_artifact_key": "control_input_transcript",
        },
        "transcript": {
            "path": (
                "reports/cut_content/apf_nfl_lineage/americans_uniform_xenia/"
                "control_input_transcript.json"
            ),
            "size_bytes": 2903,
            "sha256": (
                "2cff76c2e772214fea12a25964d0b54f8f759b398e826f0fa4630c8c52fed122"
            ),
            "schema": "apf_uniform_xenia_control_transcript/v1",
        },
    },
    {
        "id": "americans_uniform_pattern_alpha64_20260710",
        "report": {
            "path": "reports/assets/apf_uniform_pattern_xenia_runtime.json",
            "size_bytes": 12309,
            "sha256": (
                "e060398d397dfe7e6dc8aaf1ce7916922a58cfb0126b2c5d2c94456e6163e1fd"
            ),
            "schema": "apf_uniform_pattern_xenia_runtime/v1",
            "transcript_path_field": "input_transcript",
            "transcript_sha256_field": "input_transcript_sha256",
            "transcript_artifact_key": "input_transcript",
        },
        "transcript": {
            "path": (
                "reports/cut_content/apf_nfl_lineage/"
                "americans_uniform_pattern_xenia/pattern_input_transcript.json"
            ),
            "size_bytes": 2819,
            "sha256": (
                "bfc4f13f0e094d7e275f3dcf2d4dfa9524de51c5b60ba041f115683f04481be8"
            ),
            "schema": "apf_uniform_pattern_xenia_transcript/v1",
        },
    },
    {
        "id": "americans_uniform_pattern_alpha0_20260710",
        "report": {
            "path": "reports/assets/apf_uniform_pattern_alpha0_xenia_runtime.json",
            "size_bytes": 12916,
            "sha256": (
                "4ea706acad8e77fcfb0adc65d55991c151823e9ba0287a29531be6188cb256ea"
            ),
            "schema": "apf_uniform_pattern_alpha0_xenia_runtime/v1",
            "transcript_path_field": "input_transcript",
            "transcript_sha256_field": "input_transcript_sha256",
            "transcript_artifact_key": "r3_transcript",
        },
        "transcript": {
            "path": (
                "reports/cut_content/apf_nfl_lineage/"
                "americans_uniform_pattern_alpha0_xenia/r3_input_transcript.json"
            ),
            "size_bytes": 3140,
            "sha256": (
                "0621f4287afb584de8ae9749df6c999043b0132414b1fa949883953c7b781f76"
            ),
            "schema": "apf_uniform_pattern_alpha0_xenia_transcript/v1",
        },
    },
]

EXPECTED_CLAIM_BOUNDARY = {
    "legacy_reports_and_transcripts_preserved_byte_exact": True,
    "recorded_invocation_path_is_a_capture_time_path": True,
    "recorded_invocation_path_is_current_source_authority": False,
    "recovery_listing_postdates_capture": True,
    "recovery_listing_is_original_capture_session": False,
    "capture_time_hash_matches_frozen_source": True,
    "frozen_source_is_capture_byte_authority": True,
    "frozen_source_is_executed_by_validation": False,
    "controller_behavior_outside_the_recorded_input_stream_proved": False,
}


class ProvenanceError(ValueError):
    """Frozen capture provenance is missing, unsafe, or inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProvenanceError(message)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ProvenanceError(f"non-finite JSON value in {label}: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvenanceError(f"invalid JSON in {label}: {error}") from error
    require(isinstance(value, dict), f"{label} root is not an object")
    return value


def recover_source_from_session_record(session_log: Path) -> bytes:
    """Extract the frozen source from the separately retained recovery record.

    This is an optional provenance proof.  The canonical repository validator
    deliberately does not require a user's private session archive to exist.
    """

    wanted_line = EXPECTED_RECOVERY["session_output_line"]
    record_payload: bytes | None = None
    with session_log.open("rb") as stream:
        for line_number, line in enumerate(stream, 1):
            if line_number == wanted_line:
                record_payload = line
                break
    require(record_payload is not None, "recovery session output line is missing")
    record = _strict_json(record_payload, "recovery session output record")
    require(
        record.get("timestamp") == EXPECTED_RECOVERY["session_output_timestamp_utc"],
        "recovery session output timestamp differs",
    )
    require(record.get("type") == "response_item", "recovery record type differs")
    payload = record.get("payload")
    require(isinstance(payload, dict), "recovery output payload is not an object")
    require(
        payload.get("type") == "custom_tool_call_output"
        and payload.get("call_id") == EXPECTED_RECOVERY["session_output_call_id"],
        "recovery output call identity differs",
    )
    output = payload.get("output")
    require(isinstance(output, list), "recovery output blocks are missing")
    text_blocks: list[str] = []
    for block in output:
        require(isinstance(block, dict), "recovery output block is not an object")
        if block.get("type") == "input_text":
            block_text = block.get("text")
            require(isinstance(block_text, str), "recovery output text is invalid")
            text_blocks.append(block_text)
    combined = "".join(text_blocks)
    marker = "#!/usr/bin/env python3\n"
    require(combined.count(marker) == 1, "recovery source marker count differs")
    source = combined[combined.index(marker) :].encode("utf-8")
    require(len(source) == FROZEN_SOURCE_SIZE, "recovered source size differs")
    require(
        hashlib.sha256(source).hexdigest() == FROZEN_SOURCE_SHA256,
        "recovered source SHA-256 differs",
    )
    return source


def _safe_relative(value: str, label: str) -> PurePosixPath:
    require(isinstance(value, str) and value, f"{label} path is empty")
    path = PurePosixPath(value)
    require(not path.is_absolute(), f"{label} path is absolute")
    require(
        all(part not in {"", ".", ".."} for part in path.parts),
        f"{label} path has an unsafe component",
    )
    return path


def _no_symlink_parents(root: Path, relative: PurePosixPath, label: str) -> Path:
    root = root.absolute()
    current = root
    require(stat.S_ISDIR(os.lstat(root).st_mode), "validation root is not a directory")
    for part in relative.parts[:-1]:
        current = current / part
        metadata = os.lstat(current)
        require(
            stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode),
            f"{label} parent is not a real directory: {current}",
        )
    return root.joinpath(*relative.parts)


def read_bound(
    root: Path,
    relative_value: str,
    expected_size: int,
    expected_sha256: str,
    label: str,
) -> bytes:
    relative = _safe_relative(relative_value, label)
    path = _no_symlink_parents(root, relative, label)
    before_path = os.lstat(path)
    require(
        stat.S_ISREG(before_path.st_mode) and not stat.S_ISLNK(before_path.st_mode),
        f"{label} is not a regular non-symlink file",
    )
    require(before_path.st_nlink == 1, f"{label} is hardlinked")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        require(
            (before.st_dev, before.st_ino) == (before_path.st_dev, before_path.st_ino),
            f"{label} changed between path and descriptor binding",
        )
        require(stat.S_ISREG(before.st_mode), f"{label} descriptor is not regular")
        require(before.st_nlink == 1, f"{label} descriptor is hardlinked")
        require(before.st_size == expected_size, f"{label} size differs")
        chunks: list[bytes] = []
        remaining = expected_size + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    stable_fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns")
    require(
        all(getattr(before, field) == getattr(after, field) for field in stable_fields),
        f"{label} changed while being read",
    )
    require(len(payload) == expected_size, f"{label} byte count differs")
    require(
        hashlib.sha256(payload).hexdigest() == expected_sha256,
        f"{label} SHA-256 differs",
    )
    return payload


def _validate_binding(root: Path, binding: dict[str, Any]) -> None:
    report_record = binding["report"]
    transcript_record = binding["transcript"]
    report_payload = read_bound(
        root,
        report_record["path"],
        report_record["size_bytes"],
        report_record["sha256"],
        f"{binding['id']} report",
    )
    transcript_payload = read_bound(
        root,
        transcript_record["path"],
        transcript_record["size_bytes"],
        transcript_record["sha256"],
        f"{binding['id']} transcript",
    )
    report = _strict_json(report_payload, f"{binding['id']} report")
    transcript = _strict_json(transcript_payload, f"{binding['id']} transcript")
    require(report.get("schema") == report_record["schema"], "report schema differs")
    require(
        transcript.get("schema") == transcript_record["schema"],
        "transcript schema differs",
    )
    reproduction = report.get("reproduction")
    require(isinstance(reproduction, dict), "report reproduction is not an object")
    require(
        reproduction.get("controller_tool") == RECORDED_INVOCATION_PATH,
        "report capture-time controller path differs",
    )
    require(
        reproduction.get("controller_tool_sha256") == FROZEN_SOURCE_SHA256,
        "report capture-time controller hash differs",
    )
    require(
        reproduction.get(report_record["transcript_path_field"])
        == transcript_record["path"],
        "report transcript path differs",
    )
    require(
        reproduction.get(report_record["transcript_sha256_field"])
        == transcript_record["sha256"],
        "report transcript hash differs",
    )
    artifacts = report.get("artifacts")
    require(isinstance(artifacts, dict), "report artifacts is not an object")
    artifact = artifacts.get(report_record["transcript_artifact_key"])
    require(isinstance(artifact, dict), "report transcript artifact is missing")
    require(
        artifact.get("path") == transcript_record["path"]
        and artifact.get("sha256") == transcript_record["sha256"],
        "report transcript artifact differs",
    )
    controller = transcript.get("controller")
    require(isinstance(controller, dict), "transcript controller is not an object")
    require(
        controller.get("tool") == RECORDED_INVOCATION_PATH,
        "transcript capture-time controller path differs",
    )
    require(
        controller.get("sha256") == FROZEN_SOURCE_SHA256,
        "transcript capture-time controller hash differs",
    )


def validate(root: Path = ROOT, binding_id: str | None = None) -> dict[str, Any]:
    manifest_payload = read_bound(
        root,
        MANIFEST,
        MANIFEST_SIZE,
        MANIFEST_SHA256,
        "controller provenance manifest",
    )
    manifest = _strict_json(manifest_payload, "controller provenance manifest")
    require(
        set(manifest) == {"schema", "created_at", "capture_source", "bindings", "claim_boundary"},
        "controller provenance manifest keys differ",
    )
    require(
        manifest["schema"] == "apf_xenia_controller_capture_provenance/v1"
        and manifest["created_at"] == "2026-07-17",
        "controller provenance manifest identity differs",
    )
    require(
        manifest["capture_source"]
        == {
            "recorded_invocation_path": RECORDED_INVOCATION_PATH,
            "frozen_path": FROZEN_SOURCE,
            "size_bytes": FROZEN_SOURCE_SIZE,
            "sha256": FROZEN_SOURCE_SHA256,
            "recovery": EXPECTED_RECOVERY,
        },
        "controller provenance source record differs",
    )
    require(manifest["bindings"] == EXPECTED_BINDINGS, "provenance bindings differ")
    require(
        manifest["claim_boundary"] == EXPECTED_CLAIM_BOUNDARY,
        "controller provenance claim boundary differs",
    )
    source = read_bound(
        root,
        FROZEN_SOURCE,
        FROZEN_SOURCE_SIZE,
        FROZEN_SOURCE_SHA256,
        "frozen capture controller source",
    )
    try:
        source_text = source.decode("utf-8")
        ast.parse(source_text, filename=FROZEN_SOURCE)
    except (UnicodeDecodeError, SyntaxError) as error:
        raise ProvenanceError(f"frozen controller source is not valid UTF-8 Python: {error}") from error
    for marker in (
        "Persistent virtual Xbox 360-style controller for bounded Xenia testing.",
        "UInput",
        "ABS_Z",
        "ABS_RZ",
        '"LT"',
        '"RT"',
        "tap_trigger",
    ):
        require(marker in source_text, f"frozen controller lacks marker: {marker}")
    require("STICK_DIRECTIONS" not in source_text, "frozen source is an evolved successor")
    require("AFTER_PULSE" not in source_text, "frozen source is an evolved successor")

    by_id = {binding["id"]: binding for binding in EXPECTED_BINDINGS}
    require(binding_id is None or binding_id in by_id, "unknown provenance binding")
    selected = EXPECTED_BINDINGS if binding_id is None else [by_id[binding_id]]
    for binding in selected:
        _validate_binding(root, binding)
    return {
        "binding_count": len(selected),
        "binding_ids": [binding["id"] for binding in selected],
        "source_size": len(source),
        "source_sha256": hashlib.sha256(source).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binding",
        choices=[binding["id"] for binding in EXPECTED_BINDINGS],
    )
    parser.add_argument(
        "--verify-recovery-session",
        action="store_true",
        help=(
            "also verify the private later-session recovery listing under the "
            "current user's home directory"
        ),
    )
    args = parser.parse_args(argv)
    try:
        result = validate(binding_id=args.binding)
        session_verified = False
        if args.verify_recovery_session:
            session_path = Path.home() / EXPECTED_RECOVERY["session_log_home_relative"]
            recovered = recover_source_from_session_record(session_path)
            frozen = read_bound(
                ROOT,
                FROZEN_SOURCE,
                FROZEN_SOURCE_SIZE,
                FROZEN_SOURCE_SHA256,
                "frozen capture controller source",
            )
            require(recovered == frozen, "recovered and frozen source bytes differ")
            session_verified = True
        print(
            "APF_XENIA_CONTROLLER_CAPTURE_PROVENANCE_PASS "
            f"bindings={result['binding_count']} "
            f"source_size={result['source_size']} "
            f"source_sha256={result['source_sha256']} "
            "reports_unchanged=true transcripts_unchanged=true "
            "source_executed=false "
            f"recovery_session_verified={str(session_verified).lower()}"
        )
        return 0
    except (OSError, ProvenanceError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
