#!/usr/bin/env python3
"""Run and aggregate the retail-free APF 2K8 membership-consumer census.

One ``run`` invocation launches one exact, operator-pinned Xenia build against
the user's extracted APF 2K8 USA dump.  The source tree is hashed before and
afterward, Xenia receives fresh private storage/configuration roots, and the
process group is stopped at a bounded timeout.  The hook is observation-only.

Raw hook logs stay in the private run directory.  Code locations, epochs,
teams, and member slots never enter ``result.json``.  Code locations are
instead reduced to domain-separated SHA-256 consumer fingerprints.  The
``aggregate`` command compares those fingerprints across an explicitly named
scenario matrix.  Only that offline comparison can declare convergence; a
single emulator run never can.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable, Mapping, Sequence

import apf_slot43_xenia_experiment as safety


RUN_SCHEMA = "apf2k8_membership_consumer_census_run/v1"
RESULT_SCHEMA = "apf2k8_membership_consumer_census_result/v1"
STATIC_LEDGER_SCHEMA = "apf2k8_membership_consumer_static_ledger/v1"
DEFAULT_XEX_SHA256 = safety.DEFAULT_XEX_SHA256
DEFAULT_TIMEOUT_SECONDS = 180
MIN_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 900
MAX_LOG_SIZE = 256 * 1024 * 1024
MAX_MARKER_LINES = 100_000
MAX_ACCESS_EVENTS = 100_000
MARKER = "APF_MEMBERSHIP_CENSUS"
CENSUS_LOG_CVAR = "--apf_roster_membership_census_log=true"
FINGERPRINT_DOMAIN = b"APF2K8_MEMBERSHIP_CONSUMER_V1\0"
HEADLESS_SCENARIO = "boot_headless_smoke"
FULL_CENSUS_SCENARIOS = (
    "boot_headless_smoke",
    "frontend_navigation",
    "team_select",
    "roster_management",
    "depth_chart",
    "play_now_offense",
    "play_now_defense",
    "play_now_special_teams",
    "substitutions",
    "injury",
    "stats",
    "postgame",
    "cold_reload_fresh_process",
)
# Exact Linux x86-64 hook build admitted after independent source review and a
# dedicated hostile-thunk sentinel (GPR, XMM1-15, MXCSR, SysV alignment, and
# continuation). A live run refuses every other binary/commit pair. Dry-run
# admission remains available for inspecting source-tree safety without an
# emulator process.
REVIEWED_XENIA_SHA256: str | None = (
    "712df8acf4886bbc917713a7b5e120140d57b3a59a0c98e4f5ff6b5f8a47187d"
)
REVIEWED_HOOK_COMMIT: str | None = (
    "d09cae8d8374324048ef603d48a9c1696b39d552"
)
REVIEWED_STATIC_LEDGER_SHA256: str | None = None

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
HEX32_RE = re.compile(r"^[0-9a-fA-F]{8}$")
UINT_RE = re.compile(r"^(?:0|[1-9][0-9]{0,9})$")
SCENARIO_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
TOKEN_RE = re.compile(r"^([a-z0-9_]+)=([^\s,]+),?$")

ALLOWED_OPS = {"read", "write"}
ALLOWED_REGIONS = {"member", "count"}
NORMAL_ACCESS_WIDTHS = frozenset(range(1, 17))
MEMSET_ACCESS_WIDTHS = frozenset({32, 128})
ALLOWED_WIDTHS = NORMAL_ACCESS_WIDTHS | MEMSET_ACCESS_WIDTHS
OVERFLOW_FAILURES = {"event_limit", "dropped_event"}
VALIDATION_FAILURES = {
    "overflow",
    "unsupported_overlap",
    "malformed_access",
    "root_reload",
    "context_state_not_forced",
}
STATIC_DISPOSITIONS = {
    "runtime_required",
    "statically_resolved",
    "false_positive",
    "unsupported",
    "unclassified",
}
SINGLE_CLASSIFICATIONS = {
    "validation_rejected",
    "path_not_reached",
    "trace_overflow",
    "partial_coverage",
    "scenario_census_complete",
}
ALL_CLASSIFICATIONS = SINGLE_CLASSIFICATIONS | {"census_converged"}


class MembershipCensusError(ValueError):
    """A setup, protocol, or integrity error that must fail closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MembershipCensusError(message)


@dataclass(frozen=True)
class AccessProfile:
    fingerprint: str
    site_fingerprint: str
    op: str
    width: int
    region: str

    def sanitized(self) -> dict[str, object]:
        return {
            "fingerprint": self.fingerprint,
            "site_fingerprint": self.site_fingerprint,
            "op": self.op,
            "width": self.width,
            "region": self.region,
        }


@dataclass(frozen=True)
class ParsedCensus:
    marker_line_count: int
    protocol_receipt_count: int
    protocol_valid: bool
    epoch_invalidated: int
    validation_accepted: int
    validation_rejected: int
    access_event_count: int
    access_profiles: tuple[AccessProfile, ...]
    failure_counts: Mapping[str, int]
    malformed_line_count: int
    lifecycle_valid: bool
    parser_limit_reached: bool

    @property
    def overflow_seen(self) -> bool:
        return self.parser_limit_reached or any(
            self.failure_counts.get(reason, 0) for reason in OVERFLOW_FAILURES
        )

    @property
    def validation_failure_seen(self) -> bool:
        return any(
            self.failure_counts.get(reason, 0) for reason in VALIDATION_FAILURES
        )

    @property
    def fingerprints(self) -> tuple[str, ...]:
        return tuple(profile.fingerprint for profile in self.access_profiles)

    def sanitized(self) -> dict[str, object]:
        profile_counts = Counter(
            f"{profile.region}:{profile.op}:{profile.width}"
            for profile in self.access_profiles
        )
        return {
            "marker_line_count": self.marker_line_count,
            "protocol_receipt_count": self.protocol_receipt_count,
            "protocol_valid": self.protocol_valid,
            "epoch_invalidated_count": self.epoch_invalidated,
            "validation_accepted_count": self.validation_accepted,
            "validation_rejected_count": self.validation_rejected,
            "access_event_count": self.access_event_count,
            "unique_consumer_count": len(self.access_profiles),
            "consumer_fingerprints": list(self.fingerprints),
            "access_profiles": [
                profile.sanitized() for profile in self.access_profiles
            ],
            "profile_counts": dict(sorted(profile_counts.items())),
            "failure_counts": {
                reason: self.failure_counts.get(reason, 0)
                for reason in sorted(OVERFLOW_FAILURES | VALIDATION_FAILURES)
            },
            "malformed_line_count": self.malformed_line_count,
            "lifecycle_valid": self.lifecycle_valid,
            "trace_overflow_seen": self.overflow_seen,
        }


def _normalize_sha256(value: str, label: str) -> str:
    require(SHA256_RE.fullmatch(value) is not None,
            f"{label} must be exactly 64 hexadecimal characters")
    normalized = value.lower()
    require(normalized != "0" * 64, f"{label} cannot be an all-zero placeholder")
    return normalized


def _normalize_commit(value: str) -> str:
    require(COMMIT_RE.fullmatch(value) is not None,
            "hook commit must be a full 40-character hexadecimal commit")
    normalized = value.lower()
    require(normalized != "0" * 40,
            "hook commit cannot be an all-zero placeholder")
    return normalized


def _validate_scenario(value: str) -> str:
    require(SCENARIO_RE.fullmatch(value) is not None,
            "scenario must be a 1-64 character lowercase slug")
    return value


def _uint(value: str | None, label: str, *, maximum: int) -> int:
    require(value is not None and UINT_RE.fullmatch(value) is not None,
            f"{label} is not an unsigned decimal integer")
    number = int(value)
    require(number <= maximum, f"{label} exceeds its safety bound")
    return number


def _tokens(payload: str) -> dict[str, str] | None:
    values: dict[str, str] = {}
    for token in payload.split():
        match = TOKEN_RE.fullmatch(token)
        if match is None:
            return None
        name, value = match.groups()
        if name in values:
            return None
        values[name] = value
    return values


def _exact_keys(values: Mapping[str, str], expected: set[str]) -> bool:
    return set(values) == expected


def _valid_access_width(op: object, width: object) -> bool:
    if not isinstance(width, int) or isinstance(width, bool):
        return False
    return (
        width in NORMAL_ACCESS_WIDTHS
        or (op == "write" and width in MEMSET_ACCESS_WIDTHS)
    )


def _site_fingerprint(pc: str) -> str:
    payload = f"site|{pc.upper()}"
    return hashlib.sha256(FINGERPRINT_DOMAIN + payload.encode("ascii")).hexdigest()


def _consumer_fingerprint(
    *, pc: str, lr: str, op: str, width: int, region: str,
    team: int, slot: int, byte: int,
) -> str:
    payload = "|".join((
        pc.upper(), lr.upper(), op, str(width), region,
        str(team), str(slot), str(byte),
    ))
    return hashlib.sha256(FINGERPRINT_DOMAIN + payload.encode("ascii")).hexdigest()


def parse_receipt_lines(lines: Iterable[str]) -> ParsedCensus:
    """Parse hook receipts without retaining raw addresses or roster indexes."""

    marker_lines = 0
    protocol_receipts = 0
    protocol_valid = False
    invalidated = 0
    accepted = 0
    rejected = 0
    access_events = 0
    failures: Counter[str] = Counter()
    malformed = 0
    parser_limit = False
    lifecycle_valid = True
    invalidated_epoch: int | None = None
    active_epoch: int | None = None
    profiles: dict[str, AccessProfile] = {}

    for line in lines:
        marker = line.find(MARKER)
        if marker < 0:
            continue
        marker_lines += 1
        if marker_lines > MAX_MARKER_LINES:
            parser_limit = True
            break
        values = _tokens(line[marker + len(MARKER):])
        if values is None:
            malformed += 1
            continue
        receipt = values.get("receipt")

        if receipt == "protocol":
            protocol_receipts += 1
            valid = (
                marker_lines == 1
                and _exact_keys(
                    values, {"receipt", "version", "observation_only"}
                )
                and values.get("version") == "1"
                and values.get("observation_only") == "true"
            )
            protocol_valid = protocol_valid or valid
            if not valid:
                malformed += 1
            continue

        if not protocol_valid or protocol_receipts != 1:
            malformed += 1
            continue

        if receipt == "epoch_invalidated":
            if not _exact_keys(values, {"receipt", "epoch"}):
                malformed += 1
                continue
            try:
                epoch = _uint(values.get("epoch"), "epoch", maximum=0xFFFFFFFF)
                require(epoch >= 1, "epoch must be at least one")
            except MembershipCensusError:
                malformed += 1
                continue
            invalidated += 1
            if invalidated_epoch is not None:
                lifecycle_valid = False
            invalidated_epoch = epoch
            active_epoch = None
            continue

        if receipt == "validation_accepted":
            if not _exact_keys(
                values, {"receipt", "epoch", "teams", "memberships"}
            ):
                malformed += 1
                continue
            try:
                epoch = _uint(values.get("epoch"), "epoch", maximum=0xFFFFFFFF)
                require(epoch >= 1, "epoch must be at least one")
            except MembershipCensusError:
                malformed += 1
                continue
            if values.get("teams") != "40" or values.get("memberships") != "1344":
                malformed += 1
                continue
            accepted += 1
            if (
                active_epoch is not None
                or invalidated_epoch is None
                or epoch != invalidated_epoch
            ):
                lifecycle_valid = False
                active_epoch = None
            else:
                active_epoch = epoch
            continue

        if receipt == "validation_rejected":
            if not _exact_keys(values, {"receipt", "epoch", "reason"}):
                malformed += 1
                continue
            try:
                epoch = _uint(values.get("epoch"), "epoch", maximum=0xFFFFFFFF)
                require(epoch >= 1, "epoch must be at least one")
            except MembershipCensusError:
                malformed += 1
                continue
            reason = values.get("reason", "")
            if re.fullmatch(r"[a-z][a-z0-9_]{0,47}", reason) is None:
                malformed += 1
                continue
            rejected += 1
            if invalidated_epoch is None or epoch != invalidated_epoch:
                lifecycle_valid = False
            active_epoch = None
            continue

        if receipt == "census_failed":
            if not _exact_keys(values, {"receipt", "epoch", "reason"}):
                malformed += 1
                continue
            try:
                epoch = _uint(values.get("epoch"), "epoch", maximum=0xFFFFFFFF)
                require(epoch >= 1, "epoch must be at least one")
            except MembershipCensusError:
                malformed += 1
                continue
            reason = values.get("reason", "")
            if reason not in OVERFLOW_FAILURES | VALIDATION_FAILURES:
                malformed += 1
                continue
            failures[reason] += 1
            if invalidated_epoch is None or epoch != invalidated_epoch:
                lifecycle_valid = False
            active_epoch = None
            continue

        if receipt == "access":
            expected = {
                "receipt", "epoch", "pc", "lr", "op", "width",
                "region", "slot", "team", "byte",
            }
            if not _exact_keys(values, expected):
                malformed += 1
                continue
            try:
                epoch = _uint(values.get("epoch"), "epoch", maximum=0xFFFFFFFF)
                require(epoch >= 1, "epoch must be at least one")
                width = _uint(values.get("width"), "width", maximum=128)
                slot = _uint(values.get("slot"), "slot", maximum=41)
                team = _uint(values.get("team"), "team", maximum=39)
                # Member receipts use a byte-within-four-byte-slot coordinate.
                # Count receipts use the count byte's lane inside the original
                # access interval, which may be as wide as a 128-byte MEMSET.
                byte = _uint(values.get("byte"), "byte", maximum=127)
            except MembershipCensusError:
                malformed += 1
                continue
            pc = values.get("pc", "")
            lr = values.get("lr", "")
            op = values.get("op", "")
            region = values.get("region", "")
            if (
                HEX32_RE.fullmatch(pc) is None
                or HEX32_RE.fullmatch(lr) is None
                or op not in ALLOWED_OPS
                or not _valid_access_width(op, width)
                or region not in ALLOWED_REGIONS
                or int(pc, 16) == 0
                or (region == "member" and byte > 3)
                or (region == "count" and (slot != 0 or byte >= width))
            ):
                malformed += 1
                continue
            if (
                active_epoch is None
                or invalidated_epoch is None
                or epoch != active_epoch
                or epoch != invalidated_epoch
            ):
                lifecycle_valid = False
                malformed += 1
                continue
            access_events += 1
            if access_events > MAX_ACCESS_EVENTS:
                parser_limit = True
                break
            fingerprint = _consumer_fingerprint(
                pc=pc,
                lr=lr,
                op=op,
                width=width,
                region=region,
                team=team,
                slot=slot,
                byte=byte,
            )
            profiles.setdefault(
                fingerprint,
                AccessProfile(
                    fingerprint, _site_fingerprint(pc), op, width, region
                ),
            )
            continue

        malformed += 1

    ordered_profiles = tuple(profiles[key] for key in sorted(profiles))
    return ParsedCensus(
        marker_line_count=marker_lines,
        protocol_receipt_count=protocol_receipts,
        protocol_valid=protocol_valid and protocol_receipts == 1,
        epoch_invalidated=invalidated,
        validation_accepted=accepted,
        validation_rejected=rejected,
        access_event_count=access_events,
        access_profiles=ordered_profiles,
        failure_counts=dict(failures),
        malformed_line_count=malformed,
        lifecycle_valid=lifecycle_valid,
        parser_limit_reached=parser_limit,
    )


def parse_receipt_log(path: Path) -> ParsedCensus:
    log = safety._regular_file(path, "Xenia census log")
    require(log.stat().st_size <= MAX_LOG_SIZE,
            "Xenia census log exceeds the safety bound")
    with log.open("r", encoding="utf-8", errors="replace") as stream:
        return parse_receipt_lines(stream)


def classify_single(
    receipts: ParsedCensus,
    *,
    execution_acceptable: bool = True,
    source_tree_unchanged: bool = True,
    default_xex_unchanged: bool = True,
) -> tuple[str, list[str]]:
    """Classify one scenario run; this function can never claim convergence."""

    integrity_reasons: list[str] = []
    if not execution_acceptable:
        integrity_reasons.append("emulator_execution_failed")
    if not source_tree_unchanged:
        integrity_reasons.append("source_tree_changed")
    if not default_xex_unchanged:
        integrity_reasons.append("default_xex_changed")
    if integrity_reasons:
        return "validation_rejected", sorted(integrity_reasons)

    if receipts.protocol_receipt_count != 1 or not receipts.protocol_valid:
        return "validation_rejected", ["hook_protocol_receipt_missing_or_invalid"]

    if receipts.overflow_seen:
        reasons = ["trace_capacity_exceeded"]
        if receipts.failure_counts.get("dropped_event", 0):
            reasons.append("hook_reported_dropped_event")
        if receipts.failure_counts.get("event_limit", 0):
            reasons.append("hook_reported_event_limit")
        if receipts.parser_limit_reached:
            reasons.append("parser_safety_limit_reached")
        return "trace_overflow", sorted(reasons)

    rejection_reasons: list[str] = []
    if receipts.validation_rejected:
        rejection_reasons.append("hook_validation_rejected")
    if receipts.validation_failure_seen:
        rejection_reasons.append("hook_census_failed")
    if receipts.malformed_line_count:
        rejection_reasons.append("malformed_receipt")
    if not receipts.lifecycle_valid:
        rejection_reasons.append("invalid_epoch_lifecycle")
    if receipts.validation_accepted > 1:
        rejection_reasons.append("duplicate_validation_acceptance")
    if receipts.epoch_invalidated > 1:
        rejection_reasons.append("multiple_epoch_invalidations")
    if rejection_reasons:
        return "validation_rejected", sorted(rejection_reasons)

    if receipts.validation_accepted == 0 and receipts.access_event_count == 0:
        return "path_not_reached", ["validated_epoch_not_seen"]
    if receipts.validation_accepted == 1 and receipts.access_event_count > 0:
        return "scenario_census_complete", []
    return "partial_coverage", ["validated_access_not_seen"]


def build_command(
    *,
    xvfb_run: Path,
    env_executable: Path,
    xenia: Path,
    default_xex: Path,
    roots: Mapping[str, Path],
    xenia_log: Path,
) -> list[str]:
    required_roots = {"storage", "content", "cache", "tmp"}
    require(required_roots <= roots.keys(), "isolated Xenia roots are incomplete")
    command = [
        str(xvfb_run),
        "-a",
        "--server-args=-screen 0 1280x720x24",
    ]
    command.extend(safety._xenia_child_prefix(
        env_executable=env_executable,
        xenia=xenia,
        roots=roots,
    ))
    command.extend([
        "--gpu=null",
        "--apu=nop",
        "--hid=nop",
        "--fullscreen=false",
        "--portable=false",
        "--apply_title_update=false",
        "--apply_patches=false",
        "--allow_plugins=false",
        "--discord=false",
        "--mount_scratch=false",
        "--mount_memory_unit=false",
        "--license_mask=1",
        "--log_to_stdout=false",
        "--flush_log=true",
        "--log_level=2",
        "--store_all_context_values=true",
        f"--log_file={xenia_log}",
        f"--storage_root={roots['storage']}",
        f"--content_root={roots['content']}",
        f"--cache_root={roots['cache']}",
        CENSUS_LOG_CVAR,
        str(default_xex),
    ])
    return command


def _manifest(
    *,
    scenario: str,
    pass_index: int,
    timeout_seconds: int,
    dry_run: bool,
    xenia: Path,
    xenia_size: int,
    xenia_sha256: str,
    hook_commit: str,
    game_root: Path,
    default_xex: Path,
    default_xex_size: int,
    source_before: Mapping[str, object],
    command: Sequence[str],
    roots: Mapping[str, Path],
) -> dict[str, object]:
    return {
        "schema": RUN_SCHEMA,
        "scenario": scenario,
        "pass_index": pass_index,
        "dry_run": dry_run,
        "timeout_seconds": timeout_seconds,
        "toolchain": {
            "xenia_path": str(xenia),
            "xenia_size": xenia_size,
            "xenia_sha256": xenia_sha256,
            "hook_commit": hook_commit,
        },
        "source": {
            "game_directory": str(game_root),
            "default_xex": str(default_xex),
            "default_xex_size": default_xex_size,
            "default_xex_sha256": DEFAULT_XEX_SHA256,
            "tree_before": dict(source_before),
            "opened_read_only": True,
        },
        "isolation": {
            "storage_root": str(roots["storage"]),
            "content_root": str(roots["content"]),
            "cache_root": str(roots["cache"]),
            "xenia_tmp_root": str(roots["tmp"]),
            "home_root": str(roots["home"]),
            "xdg_config_root": str(roots["xdg-config"]),
            "xdg_data_root": str(roots["xdg-data"]),
            "xdg_cache_root": str(roots["xdg-cache"]),
            "fresh_empty_content_root": True,
            "xvfb_tmpdir_inherited": False,
            "xenia_tmpdir_restored_after_xvfb_setup": True,
        },
        "command": list(command),
        "safety": {
            "headless_xvfb": True,
            "observation_only_hook": True,
            "apply_title_update": False,
            "apply_patches": False,
            "allow_plugins": False,
            "discord": False,
            "apu": "nop",
            "hid": "nop",
            "gpu": "null",
            "game_files_copied": False,
            "game_files_written_by_runner": False,
            "retail_payload_embedded_in_tool": False,
        },
    }


def run_census(
    *,
    xenia_path: Path,
    expected_xenia_sha256: str,
    hook_commit: str,
    game_directory: Path,
    run_root_path: Path,
    scenario: str,
    pass_index: int = 1,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, object]:
    expected_xenia_sha256 = _normalize_sha256(
        expected_xenia_sha256, "expected Xenia SHA-256"
    )
    hook_commit = _normalize_commit(hook_commit)
    scenario = _validate_scenario(scenario)
    require(
        scenario == HEADLESS_SCENARIO,
        f"this null-GPU/null-HID runner supports only scenario {HEADLESS_SCENARIO}",
    )
    if not dry_run:
        require(
            REVIEWED_XENIA_SHA256 is not None and REVIEWED_HOOK_COMMIT is not None,
            "live census is locked until reviewed Xenia SHA/commit pins are installed",
        )
        require(
            expected_xenia_sha256 == REVIEWED_XENIA_SHA256
            and hook_commit == REVIEWED_HOOK_COMMIT,
            "requested toolchain does not match the installed reviewed pins",
        )
    require(1 <= pass_index <= 9999, "pass index must be 1 to 9999")
    require(MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS,
            f"timeout must be {MIN_TIMEOUT_SECONDS} to {MAX_TIMEOUT_SECONDS} seconds")

    game_root = safety._regular_directory(game_directory, "game directory")
    default_xex = safety._regular_file(game_root / "default.xex", "APF default.xex")
    require(default_xex.parent == game_root,
            "default.xex must be directly inside the game directory")
    xenia = safety._regular_file(xenia_path, "pinned census Xenia", executable=True)
    require(not safety._path_contains(game_root, xenia),
            "Xenia cannot be stored inside the game directory")

    xenia_sha, xenia_size = safety.sha256_regular_file(xenia, "pinned census Xenia")
    require(xenia_sha == expected_xenia_sha256,
            "Xenia binary hash does not match --xenia-sha256")
    default_sha, default_size = safety.sha256_regular_file(
        default_xex, "APF default.xex"
    )
    require(default_sha == DEFAULT_XEX_SHA256,
            "default.xex is not the supported APF 2K8 USA executable")

    source_before = safety.hash_source_tree(game_root)
    run_root = safety._create_run_root(run_root_path, game_root, xenia)
    roots = safety._create_isolated_roots(run_root)
    xvfb_run = safety._find_xvfb_run()
    env_executable = safety._find_env_executable()
    xenia_log = roots["logs"] / "xenia.log"
    launcher_log = roots["logs"] / "launcher.log"
    command = build_command(
        xvfb_run=xvfb_run,
        env_executable=env_executable,
        xenia=xenia,
        default_xex=default_xex,
        roots=roots,
        xenia_log=xenia_log,
    )
    require(not any(roots["content"].iterdir()),
            "isolated content root was not empty immediately before launch")

    manifest = _manifest(
        scenario=scenario,
        pass_index=pass_index,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
        xenia=xenia,
        xenia_size=xenia_size,
        xenia_sha256=expected_xenia_sha256,
        hook_commit=hook_commit,
        game_root=game_root,
        default_xex=default_xex,
        default_xex_size=default_size,
        source_before=source_before,
        command=command,
        roots=roots,
    )
    manifest_path = run_root / "manifest.json"
    if dry_run:
        source_after = safety.hash_source_tree(game_root)
        default_after, _ = safety.sha256_regular_file(default_xex, "APF default.xex")
        manifest["dry_run_integrity"] = {
            "tree_after": source_after,
            "tree_unchanged": source_after == source_before,
            "default_xex_unchanged": default_after == default_sha,
        }
        require(source_after == source_before and default_after == default_sha,
                "source game changed during dry-run preparation")
        safety._write_json_exclusive(manifest_path, manifest)
        return manifest

    safety._write_json_exclusive(manifest_path, manifest)
    manifest_sha256, _ = safety.sha256_regular_file(
        manifest_path, "census manifest"
    )
    require(not any(roots["content"].iterdir()),
            "isolated content root changed before launch")
    xenia_prelaunch, _ = safety.sha256_regular_file(xenia, "pinned census Xenia")
    require(xenia_prelaunch == expected_xenia_sha256,
            "Xenia binary changed after the manifest was written")
    execution = safety._launch_bounded(
        command,
        cwd=run_root,
        environment=safety._isolated_environment(roots),
        launcher_log=launcher_log,
        timeout_seconds=timeout_seconds,
    )

    post_hash_error = False
    try:
        source_after = safety.hash_source_tree(game_root)
        default_after, _ = safety.sha256_regular_file(default_xex, "APF default.xex")
    except (OSError, safety.Slot43ExperimentError):
        post_hash_error = True
        source_after = {"sha256": None}
        default_after = None

    log_parse_error = False
    xenia_log_sha256: str | None = None
    if xenia_log.is_file() and not xenia_log.is_symlink():
        try:
            xenia_log_sha256, _ = safety.sha256_regular_file(
                xenia_log, "Xenia census log"
            )
            receipts = parse_receipt_log(xenia_log)
        except (OSError, UnicodeError, MembershipCensusError,
                safety.Slot43ExperimentError):
            receipts = parse_receipt_lines(())
            log_parse_error = True
    else:
        receipts = parse_receipt_lines(())
        log_parse_error = True

    source_unchanged = not post_hash_error and source_after == source_before
    default_unchanged = not post_hash_error and default_after == default_sha
    execution_acceptable = execution.started and (
        execution.timed_out or execution.returncode == 0
    )
    classification, reasons = classify_single(
        receipts,
        execution_acceptable=execution_acceptable,
        source_tree_unchanged=source_unchanged,
        default_xex_unchanged=default_unchanged,
    )
    if post_hash_error:
        reasons.append("source_post_hash_failed")
        classification = "validation_rejected"
    if log_parse_error:
        reasons.append("xenia_log_unavailable_or_invalid")
        classification = "validation_rejected"
    reasons = sorted(set(reasons))

    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "mode": "single",
        "scenario": scenario,
        "pass_index": pass_index,
        "classification": classification,
        "reason_codes": reasons,
        "toolchain": {
            "xenia_sha256": expected_xenia_sha256,
            "hook_commit": hook_commit,
            "default_xex_sha256": DEFAULT_XEX_SHA256,
        },
        "execution": {
            "started": execution.started,
            "timed_out": execution.timed_out,
            "returncode": execution.returncode,
            "duration_ms": execution.duration_ms,
            "termination": execution.termination,
            "timeout_seconds": timeout_seconds,
        },
        "integrity": {
            "source_tree_sha256_before": source_before["sha256"],
            "source_tree_sha256_after": source_after.get("sha256"),
            "source_tree_unchanged": source_unchanged,
            "default_xex_sha256_before": default_sha,
            "default_xex_sha256_after": default_after,
            "default_xex_unchanged": default_unchanged,
            "runner_direct_write_calls_to_source": False,
        },
        "receipts": receipts.sanitized(),
        "artifacts": {
            "manifest": "manifest.json",
            "xenia_log": "logs/xenia.log",
            "launcher_log": "logs/launcher.log",
            "manifest_sha256": manifest_sha256,
            "xenia_log_sha256": xenia_log_sha256,
            "raw_logs_private": True,
        },
        "claims": {
            "scenario_consumer_path_observed": (
                classification == "scenario_census_complete"
            ),
            "headless_boot_trace_captured": (
                classification == "scenario_census_complete"
            ),
            "operator_scenario_coverage_proved": False,
            "global_census_converged": False,
            "all_roster_consumers_extended": False,
            "true_53_man_rosters_proved": False,
            "retail_game_bytes_copied_by_runner": False,
            "retail_game_bytes_embedded_in_result": False,
            "raw_guest_locations_embedded_in_result": False,
        },
    }
    safety._write_json_exclusive(run_root / "result.json", result)
    return result


def _load_run_bundle(path: Path) -> dict[str, object]:
    run_root = safety._regular_directory(path, "census run root")
    result_path = safety._regular_file(run_root / "result.json", "census result")
    require(result_path.stat().st_size <= 16 * 1024 * 1024,
            "census result exceeds the safety bound")
    try:
        document = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MembershipCensusError(f"census result is not valid JSON: {exc}") from exc
    require(isinstance(document, dict), "census result must be a JSON object")
    require(document.get("schema") == RESULT_SCHEMA,
            "census result schema is not supported")
    require(document.get("mode") == "single",
            "aggregate inputs must be single-run census results")
    scenario = document.get("scenario")
    require(isinstance(scenario, str), "census result scenario is missing")
    _validate_scenario(scenario)
    pass_index = document.get("pass_index")
    require(isinstance(pass_index, int) and not isinstance(pass_index, bool)
            and 1 <= pass_index <= 9999,
            "census result pass index is invalid")
    classification = document.get("classification")
    require(classification in SINGLE_CLASSIFICATIONS,
            "census result classification is invalid")

    toolchain = document.get("toolchain")
    require(isinstance(toolchain, dict), "census result toolchain is missing")
    _normalize_sha256(str(toolchain.get("xenia_sha256", "")), "Xenia SHA-256")
    _normalize_commit(str(toolchain.get("hook_commit", "")))
    require(toolchain.get("default_xex_sha256") == DEFAULT_XEX_SHA256,
            "census result XEX pin does not match")

    receipts = document.get("receipts")
    require(isinstance(receipts, dict), "census result receipts are missing")
    fingerprints = receipts.get("consumer_fingerprints")
    require(isinstance(fingerprints, list),
            "census result consumer fingerprints are missing")
    normalized: list[str] = []
    for fingerprint in fingerprints:
        require(isinstance(fingerprint, str)
                and SHA256_RE.fullmatch(fingerprint) is not None,
                "census result contains an invalid consumer fingerprint")
        normalized.append(fingerprint.lower())
    require(normalized == sorted(set(normalized)),
            "census result consumer fingerprints are not canonical")
    require(receipts.get("unique_consumer_count") == len(normalized),
            "census result consumer count does not match its fingerprints")
    require(receipts.get("protocol_receipt_count") == 1
            and receipts.get("protocol_valid") is True,
            "census result lacks the exact observation-only hook protocol receipt")
    profiles = receipts.get("access_profiles")
    require(isinstance(profiles, list),
            "census result access profiles are missing")
    profile_fingerprints: list[str] = []
    for profile in profiles:
        require(isinstance(profile, dict),
                "census result contains an invalid access profile")
        fingerprint = profile.get("fingerprint")
        site_fingerprint = profile.get("site_fingerprint")
        require(isinstance(fingerprint, str)
                and SHA256_RE.fullmatch(fingerprint) is not None,
                "census result access fingerprint is invalid")
        require(isinstance(site_fingerprint, str)
                and SHA256_RE.fullmatch(site_fingerprint) is not None,
                "census result site fingerprint is invalid")
        op = profile.get("op")
        width = profile.get("width")
        require(isinstance(op, str) and op in ALLOWED_OPS,
                "census result access operation is invalid")
        require(profile.get("region") in ALLOWED_REGIONS,
                "census result access region is invalid")
        require(_valid_access_width(op, width),
                "census result access width is invalid")
        profile_fingerprints.append(fingerprint.lower())
    require(sorted(profile_fingerprints) == normalized,
            "census result profiles do not match its consumer fingerprints")
    access_event_count = receipts.get("access_event_count")
    require(isinstance(access_event_count, int)
            and not isinstance(access_event_count, bool)
            and access_event_count >= len(normalized),
            "census result access count is invalid")
    if classification == "scenario_census_complete":
        require(receipts.get("validation_accepted_count") == 1
                and access_event_count > 0,
                "complete census result lacks validated access evidence")
    integrity = document.get("integrity")
    require(isinstance(integrity, dict),
            "census result integrity receipt is missing")
    source_tree_before = _normalize_sha256(
        str(integrity.get("source_tree_sha256_before", "")),
        "source-tree before SHA-256",
    )
    source_tree_after = _normalize_sha256(
        str(integrity.get("source_tree_sha256_after", "")),
        "source-tree after SHA-256",
    )
    default_xex_before = _normalize_sha256(
        str(integrity.get("default_xex_sha256_before", "")),
        "default.xex before SHA-256",
    )
    default_xex_after = _normalize_sha256(
        str(integrity.get("default_xex_sha256_after", "")),
        "default.xex after SHA-256",
    )
    require(source_tree_before == source_tree_after,
            "source-tree before/after hashes differ")
    require(default_xex_before == default_xex_after == DEFAULT_XEX_SHA256,
            "default.xex before/after hashes do not match the supported XEX")
    require(integrity.get("source_tree_unchanged") is True
            and integrity.get("default_xex_unchanged") is True,
            "aggregate input did not preserve its source game")
    claims = document.get("claims")
    require(isinstance(claims, dict)
            and claims.get("retail_game_bytes_embedded_in_result") is False
            and claims.get("raw_guest_locations_embedded_in_result") is False,
            "aggregate input lacks retail-free sanitization claims")

    artifacts = document.get("artifacts")
    require(isinstance(artifacts, dict)
            and artifacts.get("manifest") == "manifest.json"
            and artifacts.get("xenia_log") == "logs/xenia.log",
            "census result artifact map is invalid")
    expected_manifest_sha = _normalize_sha256(
        str(artifacts.get("manifest_sha256", "")), "manifest SHA-256"
    )
    expected_log_sha = _normalize_sha256(
        str(artifacts.get("xenia_log_sha256", "")), "Xenia log SHA-256"
    )
    manifest_path = safety._regular_file(
        run_root / "manifest.json", "census manifest"
    )
    log_path = safety._regular_file(
        run_root / "logs" / "xenia.log", "Xenia census log"
    )
    manifest_sha, _ = safety.sha256_regular_file(manifest_path, "census manifest")
    log_sha, _ = safety.sha256_regular_file(log_path, "Xenia census log")
    require(manifest_sha == expected_manifest_sha,
            "census manifest hash does not match result")
    require(log_sha == expected_log_sha,
            "Xenia census log hash does not match result")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MembershipCensusError(f"census manifest is not valid JSON: {exc}") from exc
    require(isinstance(manifest, dict) and manifest.get("schema") == RUN_SCHEMA,
            "census manifest schema is not supported")
    require(manifest.get("dry_run") is False,
            "aggregate input cannot be a dry-run manifest")
    require(manifest.get("scenario") == scenario
            and manifest.get("pass_index") == pass_index,
            "manifest scenario/pass does not match result")
    manifest_toolchain = manifest.get("toolchain")
    require(isinstance(manifest_toolchain, dict)
            and manifest_toolchain.get("xenia_sha256")
            == toolchain.get("xenia_sha256")
            and manifest_toolchain.get("hook_commit")
            == toolchain.get("hook_commit"),
            "manifest toolchain does not match result")
    manifest_source = manifest.get("source")
    require(isinstance(manifest_source, dict)
            and manifest_source.get("default_xex_sha256") == DEFAULT_XEX_SHA256
            and manifest_source.get("opened_read_only") is True,
            "manifest source admission is invalid")
    manifest_tree_before = manifest_source.get("tree_before")
    require(isinstance(manifest_tree_before, dict),
            "manifest source-tree receipt is missing")
    manifest_tree_sha = _normalize_sha256(
        str(manifest_tree_before.get("sha256", "")),
        "manifest source-tree SHA-256",
    )
    require(manifest_tree_sha == source_tree_before,
            "manifest source-tree hash does not match result")
    safety_claims = manifest.get("safety")
    require(isinstance(safety_claims, dict)
            and safety_claims.get("observation_only_hook") is True
            and safety_claims.get("apply_title_update") is False
            and safety_claims.get("apply_patches") is False
            and safety_claims.get("allow_plugins") is False
            and safety_claims.get("game_files_written_by_runner") is False,
            "manifest safety contract is invalid")
    command = manifest.get("command")
    require(isinstance(command, list)
            and CENSUS_LOG_CVAR in command
            and "--store_all_context_values=true" in command,
            "manifest command lacks the exact census/context flags")

    reparsed = parse_receipt_log(log_path)
    require(reparsed.sanitized() == receipts,
            "raw hook log does not reproduce result receipts")
    execution = document.get("execution")
    require(isinstance(execution, dict), "census result execution is missing")
    execution_acceptable = execution.get("started") is True and (
        execution.get("timed_out") is True or execution.get("returncode") == 0
    )
    recomputed_classification, recomputed_reasons = classify_single(
        reparsed,
        execution_acceptable=execution_acceptable,
        source_tree_unchanged=True,
        default_xex_unchanged=True,
    )
    require(recomputed_classification == classification
            and sorted(document.get("reason_codes", [])) == recomputed_reasons,
            "raw hook log does not reproduce result classification")
    return document


def _load_static_ledger(path: Path) -> tuple[dict[str, object], str]:
    ledger_path = safety._regular_file(path, "static candidate ledger")
    require(ledger_path.stat().st_size <= 4 * 1024 * 1024,
            "static candidate ledger exceeds the safety bound")
    try:
        document = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MembershipCensusError(
            f"static candidate ledger is not valid JSON: {exc}"
        ) from exc
    require(isinstance(document, dict),
            "static candidate ledger must be a JSON object")
    require(document.get("schema") == STATIC_LEDGER_SCHEMA,
            "static candidate ledger schema is not supported")
    require(document.get("default_xex_sha256") == DEFAULT_XEX_SHA256,
            "static candidate ledger XEX pin does not match")
    inventory_id = document.get("inventory_id")
    require(isinstance(inventory_id, str),
            "static candidate ledger inventory id is missing")
    _validate_scenario(inventory_id)
    candidates = document.get("candidates")
    require(isinstance(candidates, list) and candidates,
            "static candidate ledger needs at least one candidate")
    seen: set[str] = set()
    for candidate in candidates:
        require(isinstance(candidate, dict)
                and set(candidate) == {"site_fingerprint", "disposition"},
                "static candidate ledger entry has an invalid shape")
        site = candidate.get("site_fingerprint")
        disposition = candidate.get("disposition")
        require(isinstance(site, str) and SHA256_RE.fullmatch(site) is not None,
                "static candidate ledger site fingerprint is invalid")
        site = site.lower()
        require(site not in seen,
                "static candidate ledger contains a duplicate candidate")
        seen.add(site)
        require(disposition in STATIC_DISPOSITIONS,
                "static candidate ledger disposition is invalid")
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return document, digest


def aggregate_census_results(
    *,
    input_paths: Sequence[Path],
    required_scenarios: Sequence[str],
    convergence_passes: int = 2,
    static_ledger_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, object]:
    require(input_paths, "aggregate mode needs at least one census result")
    require(required_scenarios,
            "aggregate mode needs at least one --required-scenario")
    require(2 <= convergence_passes <= 10,
            "convergence passes must be 2 to 10")
    required = tuple(_validate_scenario(value) for value in required_scenarios)
    require(len(set(required)) == len(required),
            "required scenarios must be unique")
    full_matrix_requested = (
        len(required) == len(FULL_CENSUS_SCENARIOS)
        and set(required) == set(FULL_CENSUS_SCENARIOS)
    )

    documents = [_load_run_bundle(path) for path in input_paths]
    pins = {
        (
            document["toolchain"]["xenia_sha256"],
            document["toolchain"]["hook_commit"],
            document["toolchain"]["default_xex_sha256"],
        )
        for document in documents
    }
    require(len(pins) == 1,
            "all aggregate inputs must use the same Xenia, hook, and XEX pins")
    xenia_sha256, hook_commit, default_xex_sha256 = next(iter(pins))
    toolchain_reviewed = (
        REVIEWED_XENIA_SHA256 is not None
        and REVIEWED_HOOK_COMMIT is not None
        and xenia_sha256 == REVIEWED_XENIA_SHA256
        and hook_commit == REVIEWED_HOOK_COMMIT
    )

    ledger: dict[str, object] | None = None
    ledger_sha256: str | None = None
    if static_ledger_path is not None:
        ledger, ledger_sha256 = _load_static_ledger(static_ledger_path)
    static_ledger_reviewed = (
        ledger_sha256 is not None
        and REVIEWED_STATIC_LEDGER_SHA256 is not None
        and ledger_sha256 == REVIEWED_STATIC_LEDGER_SHA256
    )

    by_scenario: dict[str, dict[int, dict[str, object]]] = {}
    for document in documents:
        scenario = str(document["scenario"])
        pass_index = int(document["pass_index"])
        passes = by_scenario.setdefault(scenario, {})
        require(pass_index not in passes,
                f"duplicate pass index for scenario {scenario}")
        passes[pass_index] = document

    classifications = {str(document["classification"]) for document in documents}
    reasons: list[str] = []
    matrix_cycle_indices: list[int] = []
    runtime_trace_stable = False
    if "validation_rejected" in classifications:
        classification = "validation_rejected"
        reasons.append("input_validation_rejected")
    elif "trace_overflow" in classifications:
        classification = "trace_overflow"
        reasons.append("input_trace_overflow")
    else:
        missing = [scenario for scenario in required if scenario not in by_scenario]
        if missing:
            classification = "partial_coverage"
            reasons.append("required_scenario_missing")
        else:
            complete_indexes = [
                {
                    index for index, document in by_scenario[scenario].items()
                    if document["classification"] == "scenario_census_complete"
                }
                for scenario in required
            ]
            shared = set.intersection(*complete_indexes) if complete_indexes else set()
            matrix_cycle_indices = sorted(shared)
            if len(matrix_cycle_indices) < convergence_passes:
                classification = "partial_coverage"
                reasons.append("insufficient_complete_matrix_cycles")
            else:
                final_cycles = matrix_cycle_indices[-convergence_passes:]
                cycle_sets: list[frozenset[str]] = []
                for pass_index in final_cycles:
                    fingerprint_union: set[str] = set()
                    for scenario in required:
                        fingerprint_union.update(
                            by_scenario[scenario][pass_index]["receipts"][
                                "consumer_fingerprints"
                            ]
                        )
                    cycle_sets.append(frozenset(fingerprint_union))
                runtime_trace_stable = all(
                    current == cycle_sets[0] for current in cycle_sets[1:]
                )
                if not runtime_trace_stable:
                    classification = "partial_coverage"
                    reasons.append("complete_matrix_consumer_set_still_changing")
                else:
                    classification = "partial_coverage"

    union: set[str] = set()
    observed_sites: set[str] = set()
    scenario_rows: list[dict[str, object]] = []
    for scenario in required:
        passes = by_scenario.get(scenario, {})
        complete_passes = [
            document for _, document in sorted(passes.items())
            if document["classification"] == "scenario_census_complete"
        ]
        final_sets = [
            frozenset(document["receipts"]["consumer_fingerprints"])
            for document in complete_passes[-convergence_passes:]
        ]
        stable = (
            len(final_sets) == convergence_passes
            and all(current == final_sets[0] for current in final_sets[1:])
        )
        scenario_union: set[str] = set()
        for document in complete_passes:
            scenario_union.update(document["receipts"]["consumer_fingerprints"])
            observed_sites.update(
                profile["site_fingerprint"]
                for profile in document["receipts"]["access_profiles"]
            )
        union.update(scenario_union)
        scenario_rows.append({
            "scenario": scenario,
            "observed_pass_count": len(passes),
            "complete_pass_count": len(complete_passes),
            "final_passes_stable": stable,
            "unique_consumer_count": len(scenario_union),
        })

    static_candidate_count = 0
    accounted_candidate_count = 0
    unaccounted_candidate_count = 0
    if ledger is not None:
        candidates = ledger["candidates"]
        static_candidate_count = len(candidates)
        for candidate in candidates:
            site = candidate["site_fingerprint"].lower()
            disposition = candidate["disposition"]
            accounted = site in observed_sites or disposition in {
                "statically_resolved", "false_positive", "unsupported"
            }
            if accounted:
                accounted_candidate_count += 1
            else:
                unaccounted_candidate_count += 1

    if classification == "partial_coverage" and runtime_trace_stable:
        if not full_matrix_requested:
            reasons.append("full_scenario_matrix_required")
        elif not toolchain_reviewed:
            reasons.append("reviewed_toolchain_pin_required")
        elif ledger is None:
            reasons.append("static_candidate_ledger_required")
        elif not static_ledger_reviewed:
            reasons.append("reviewed_static_ledger_pin_required")
        elif unaccounted_candidate_count:
            reasons.append("static_candidate_coverage_incomplete")
        else:
            classification = "census_converged"

    result: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "mode": "aggregate",
        "classification": classification,
        "reason_codes": sorted(set(reasons)),
        "required_scenarios": list(required),
        "convergence_passes": convergence_passes,
        "input_result_count": len(documents),
        "toolchain": {
            "xenia_sha256": xenia_sha256,
            "hook_commit": hook_commit,
            "default_xex_sha256": default_xex_sha256,
        },
        "coverage": {
            "scenarios": scenario_rows,
            "complete_matrix_cycle_count": len(matrix_cycle_indices),
            "complete_matrix_cycle_indices": matrix_cycle_indices,
            "runtime_trace_stable": runtime_trace_stable,
            "full_scenario_matrix_requested": full_matrix_requested,
            "unique_consumer_count": len(union),
            "consumer_fingerprints": sorted(union),
            "static_ledger": {
                "present": ledger is not None,
                "sha256": ledger_sha256,
                "candidate_count": static_candidate_count,
                "accounted_candidate_count": accounted_candidate_count,
                "unaccounted_candidate_count": unaccounted_candidate_count,
                "reviewed_pin_matched": static_ledger_reviewed,
            },
            "reviewed_toolchain_pin_matched": toolchain_reviewed,
        },
        "claims": {
            "global_census_converged": classification == "census_converged",
            "runtime_trace_stable": runtime_trace_stable,
            "full_scenario_matrix_complete": (
                full_matrix_requested and runtime_trace_stable
            ),
            "static_candidate_inventory_accounted": (
                static_ledger_reviewed and unaccounted_candidate_count == 0
            ),
            "reviewed_static_ledger_pin_matched": static_ledger_reviewed,
            "reviewed_toolchain_pin_matched": toolchain_reviewed,
            "convergence_decided_offline_across_runs": True,
            "all_roster_consumers_extended": False,
            "true_53_man_rosters_proved": False,
            "retail_game_bytes_embedded_in_result": False,
            "raw_guest_locations_embedded_in_result": False,
        },
    }
    if output_path is not None:
        candidate = output_path.expanduser()
        require(candidate.name not in {"", ".", ".."},
                "aggregate output needs a file name")
        require(not candidate.exists() and not candidate.is_symlink(),
                "aggregate output must be a new path")
        parent = safety._regular_directory(candidate.parent, "aggregate output parent")
        safety._write_json_exclusive(parent / candidate.name, result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run one isolated scenario pass")
    run.add_argument("--xenia", required=True, type=Path,
                     help="custom membership-census Xenia binary")
    run.add_argument("--xenia-sha256", required=True,
                     help="reviewed SHA-256 of that exact binary")
    run.add_argument("--hook-commit", required=True,
                     help="full reviewed 40-character Xenia source commit")
    run.add_argument("--game-dir", required=True, type=Path,
                     help="your extracted APF 2K8 game directory")
    run.add_argument("--run-root", required=True, type=Path,
                     help="new private directory for this run")
    run.add_argument("--scenario", required=True,
                     help=f"must currently be exactly: {HEADLESS_SCENARIO}")
    run.add_argument("--pass-index", type=int, default=1)
    run.add_argument("--timeout-seconds", type=int,
                     default=DEFAULT_TIMEOUT_SECONDS)
    run.add_argument("--dry-run", action="store_true",
                     help="write the manifest without launching Xenia")

    aggregate = subparsers.add_parser(
        "aggregate", help="compare sanitized single-run results"
    )
    aggregate.add_argument("--input", required=True, action="append", type=Path,
                           help="private run root; repeat for every scenario/pass")
    aggregate.add_argument("--required-scenario", required=True, action="append",
                           help="scenario required for convergence")
    aggregate.add_argument("--convergence-passes", type=int, default=2)
    aggregate.add_argument(
        "--static-ledger", type=Path,
        help="private sanitized static-candidate classification ledger",
    )
    aggregate.add_argument("--output", required=True, type=Path,
                           help="new path for the sanitized aggregate result")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run":
            document = run_census(
                xenia_path=args.xenia,
                expected_xenia_sha256=args.xenia_sha256,
                hook_commit=args.hook_commit,
                game_directory=args.game_dir,
                run_root_path=args.run_root,
                scenario=args.scenario,
                pass_index=args.pass_index,
                timeout_seconds=args.timeout_seconds,
                dry_run=args.dry_run,
            )
        else:
            document = aggregate_census_results(
                input_paths=args.input,
                required_scenarios=args.required_scenario,
                convergence_passes=args.convergence_passes,
                static_ledger_path=args.static_ledger,
                output_path=args.output,
            )
    except (OSError, MembershipCensusError, safety.Slot43ExperimentError,
            subprocess.SubprocessError) as exc:
        print(f"APF_MEMBERSHIP_CENSUS_REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(document, indent=2, sort_keys=True))
    classification = document.get("classification")
    if classification in {"validation_rejected", "trace_overflow"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
