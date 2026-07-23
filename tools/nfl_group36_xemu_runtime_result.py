#!/usr/bin/env python3
"""Validate the bounded NFL 2K5 group36 paired xemu result envelope.

The validator does not launch xemu and never infers a runtime claim from an
offline XISO proof.  Every observed run must be pinned independently on the
command line by XISO, config, HDD, screenshot paths, sizes, and SHA-256 values.
File rehashing is optional and explicit because the checked partial result is a
frozen evidence description, not permission to touch a live emulator session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ID = "nfl2k5_group36_xemu_runtime_result/v1"
SCHEMA_URI = "urn:nfl2k5-group36-xemu-runtime-result:v1"
SCHEMA_PATH = ROOT / "reports/specs/nfl2k5_group36_xemu_runtime_result.v1.schema.json"
SCHEMA_SIZE = 6_934
SCHEMA_SHA256 = "ca553ac95199813fec740a6eca305f4860daf21f062303ce2d98c689af3854b1"
MAX_RESULT_BYTES = 256 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

RUN_NAMES = ("control", "expanded_wall")
OUTCOME_ORDER = ("boot_acceptance", "selector_skip_negative", "target_visible")
SCREENSHOT_ROLES = {
    "selector_after",
    "selector_before",
    "selector_intermediate",
    "target_visible",
    "title_or_gameplay",
}

PROFILE = {
    "control": {
        "profile": "retail_control",
        "xiso_sha256": "32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5",
        "xiso_size": 6_300_499_968,
    },
    "expanded_wall": {
        "profile": "expanded_wall",
        "xiso_sha256": "3c2917114ec7005e21c24c7fdf971adfdd54c051e89ecf2c4f93beb64a73dc16",
        "xiso_size": 6_300_499_968,
    },
}

PAIR = {
    "dispatch": {
        "after_asset_code": "s42",
        "before_asset_code": "s18",
        "finding": "s42 causes roster index 18 to disappear from Quick Game cycling",
        "roster_record_index": 18,
    },
    "id": "nfl2k5_group36_s42_control_expanded/v1",
    "target": {
        "outer_filename": "s42nd.iff",
        "outer_id": "0xe4d6b0bc",
        "outer_index": 3280,
        "stadium": "Super Bowl 2006 Stadium",
        "time_of_day": "Night",
        "weather": "Clear",
    },
}

SELECTOR_OBSERVATION = {
    "after_visible_label": "Jets Stadium",
    "before_visible_label": "Jets Stadium",
    "finding": "s42 causes roster index 18 to disappear from Quick Game cycling",
    "intermediate_visible_label": "Louisiana Super Dome",
    "replacement_asset_code": "s42",
    "rewritten_record_presented": False,
    "roster_record_index": 18,
}

CLAIM_KEYS = {
    "control_selector_skip_negative_observed",
    "control_target_visible",
    "expanded_selector_skip_negative_observed",
    "expanded_target_visible",
    "geometry_visibility_proved",
    "original_xbox_hardware_proved",
    "paired_target_visible",
    "production_ready",
    "s42_index18_quick_game_skip_observed",
    "target_outer_loaded_proved",
    "xemu_boot_acceptance_proved",
}


class ResultError(ValueError):
    """Result schema, evidence identity, or claim-boundary failure."""


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


def load_result(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    require(0 < len(raw) <= MAX_RESULT_BYTES, "result size is outside the bounded range")

    def reject_constant(value: str) -> None:
        raise ResultError(f"non-JSON numeric constant: {value}")

    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ResultError(f"invalid result JSON: {exc}") from exc
    require(isinstance(value, dict), "result top level must be an object")
    canonical = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    require(raw == canonical, "result must be canonical sorted UTF-8 JSON")
    return value


def validate_schema_identity() -> None:
    require(SCHEMA_PATH.is_file() and not SCHEMA_PATH.is_symlink(), "schema is absent or a symlink")
    require(SCHEMA_PATH.stat().st_size == SCHEMA_SIZE, "schema size identity drift")
    require(sha256_file(SCHEMA_PATH) == SCHEMA_SHA256, "schema SHA-256 identity drift")
    schema = json.loads(SCHEMA_PATH.read_bytes())
    require(schema.get("$id") == SCHEMA_URI, "schema URI drift")


def _exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == keys, f"{label} key set differs")
    return value


def _safe_relative_path(value: Any, label: str) -> str:
    require(isinstance(value, str) and value and "\x00" not in value, f"{label} path is invalid")
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


def _screenshots(value: Any, label: str) -> list[dict[str, Any]]:
    require(isinstance(value, list), f"{label} must be an array")
    result: list[dict[str, Any]] = []
    roles: list[str] = []
    paths: list[str] = []
    for index, raw in enumerate(value):
        row = _exact_keys(raw, {"path", "role", "sha256", "size"}, f"{label}[{index}]")
        _safe_relative_path(row["path"], f"{label}[{index}]")
        require(row["role"] in SCREENSHOT_ROLES, f"{label}[{index}] role is invalid")
        require(type(row["size"]) is int and row["size"] > 0, f"{label}[{index}] size is invalid")
        require(isinstance(row["sha256"], str) and SHA256_RE.fullmatch(row["sha256"]),
                f"{label}[{index}] SHA-256 is invalid")
        roles.append(row["role"])
        paths.append(row["path"])
        result.append(row)
    require(roles == sorted(roles) and len(roles) == len(set(roles)),
            f"{label} roles must be unique and sorted")
    require(len(paths) == len(set(paths)), f"{label} paths must be unique")
    return result


def _outcome(value: Any, run_name: str, screenshot_roles: set[str]) -> dict[str, Any]:
    row = _exact_keys(
        value,
        {"evidence_screenshot_roles", "kind", "observation"},
        f"runs.{run_name}.outcome",
    )
    kind = row["kind"]
    require(kind in OUTCOME_ORDER, f"runs.{run_name} outcome kind is invalid")
    roles = row["evidence_screenshot_roles"]
    require(isinstance(roles, list) and roles and roles == sorted(roles)
            and len(roles) == len(set(roles)),
            f"runs.{run_name}.{kind} evidence roles must be nonempty, unique, and sorted")
    require(all(role in screenshot_roles for role in roles),
            f"runs.{run_name}.{kind} references an absent screenshot role")
    observation = row["observation"]
    require(isinstance(observation, dict), f"runs.{run_name}.{kind} observation must be an object")

    if kind == "boot_acceptance":
        require(set(observation) == {"clean_shutdown_observed", "reached"},
                f"runs.{run_name}.boot_acceptance observation keys differ")
        require(observation == {
            "clean_shutdown_observed": True,
            "reached": "rendered_title_or_gameplay",
        }, f"runs.{run_name}.boot_acceptance observation differs")
        require("title_or_gameplay" in roles,
                f"runs.{run_name}.boot_acceptance lacks title/gameplay screenshot")
    elif kind == "selector_skip_negative":
        require(observation == SELECTOR_OBSERVATION,
                f"runs.{run_name}.selector_skip_negative observation differs")
        require({"selector_before", "selector_intermediate", "selector_after"}.issubset(roles),
                f"runs.{run_name}.selector_skip_negative lacks the three selector roles")
    else:
        require(set(observation) == {
            "geometry_difference_visible",
            "matched_pair_id",
            "outer_filename",
            "stadium",
            "time_of_day",
            "weather",
        }, f"runs.{run_name}.target_visible observation keys differ")
        require(type(observation["geometry_difference_visible"]) is bool,
                f"runs.{run_name}.target_visible geometry flag must be boolean")
        require(isinstance(observation["matched_pair_id"], str)
                and observation["matched_pair_id"],
                f"runs.{run_name}.target_visible pair ID is invalid")
        require({key: observation[key] for key in (
            "outer_filename", "stadium", "time_of_day", "weather"
        )} == {
            "outer_filename": "s42nd.iff",
            "stadium": "Super Bowl 2006 Stadium",
            "time_of_day": "Night",
            "weather": "Clear",
        }, f"runs.{run_name}.target_visible route differs")
        require("target_visible" in roles,
                f"runs.{run_name}.target_visible lacks target screenshot")
        if run_name == "control":
            require(observation["geometry_difference_visible"] is False,
                    "control target-visible witness cannot claim a diagnostic difference")
    return row


def derive_claims(runs: dict[str, dict[str, Any]]) -> dict[str, bool]:
    kinds = {
        name: {row["kind"] for row in runs[name]["outcomes"]}
        for name in RUN_NAMES
    }
    control_target = "target_visible" in kinds["control"]
    expanded_target = "target_visible" in kinds["expanded_wall"]
    target_rows = {
        name: next((row for row in runs[name]["outcomes"]
                    if row["kind"] == "target_visible"), None)
        for name in RUN_NAMES
    }
    pair_visible = False
    geometry_visible = False
    if control_target and expanded_target:
        control_id = target_rows["control"]["observation"]["matched_pair_id"]
        expanded_id = target_rows["expanded_wall"]["observation"]["matched_pair_id"]
        pair_visible = control_id == expanded_id
        geometry_visible = (
            pair_visible
            and target_rows["expanded_wall"]["observation"]["geometry_difference_visible"]
            and not target_rows["control"]["observation"]["geometry_difference_visible"]
        )
    control_skip = "selector_skip_negative" in kinds["control"]
    expanded_skip = "selector_skip_negative" in kinds["expanded_wall"]
    return {
        "control_selector_skip_negative_observed": control_skip,
        "control_target_visible": control_target,
        "expanded_selector_skip_negative_observed": expanded_skip,
        "expanded_target_visible": expanded_target,
        "geometry_visibility_proved": geometry_visible,
        "original_xbox_hardware_proved": False,
        "paired_target_visible": pair_visible,
        "production_ready": False,
        "s42_index18_quick_game_skip_observed": control_skip or expanded_skip,
        "target_outer_loaded_proved": control_target or expanded_target,
        "xemu_boot_acceptance_proved": any(
            "boot_acceptance" in kinds[name] for name in RUN_NAMES
        ),
    }


def derive_status(claims: dict[str, bool]) -> str:
    if claims["paired_target_visible"]:
        return "target_visible"
    if claims["s42_index18_quick_game_skip_observed"]:
        return "selector_skip_negative"
    if claims["xemu_boot_acceptance_proved"]:
        return "boot_acceptance"
    return "unobserved"


def _verify_file(root: Path, row: dict[str, Any], label: str) -> None:
    path = root / row["path"]
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ResultError(f"{label} cannot be stated: {exc}") from exc
    require(stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode),
            f"{label} is not a non-symlink regular file")
    require(metadata.st_size == row["size"], f"{label} size differs")
    require(sha256_file(path) == row["sha256"], f"{label} SHA-256 differs")


def validate_document(
    document: dict[str, Any],
    pins: dict[str, dict[str, Any]] | None = None,
    *,
    verify_files: bool = False,
    root: Path = ROOT,
) -> dict[str, Any]:
    _exact_keys(document, {"claims", "date", "emulator", "pair", "runs", "schema", "status"},
                "result")
    require(document["schema"] == SCHEMA_ID, "result schema differs")
    require(document["date"] == "2026-07-13", "result date differs")
    require(document["emulator"] == {
        "application": "app.xemu.xemu",
        "version": "0.8.135",
    }, "emulator identity differs")
    require(document["pair"] == PAIR, "paired target/dispatch contract differs")
    runs = _exact_keys(document["runs"], set(RUN_NAMES), "runs")

    for name in RUN_NAMES:
        run = _exact_keys(
            runs[name],
            {"artifacts", "observation_status", "outcomes", "profile", "reason"},
            f"runs.{name}",
        )
        require(run["profile"] == PROFILE[name]["profile"], f"runs.{name} profile differs")
        require(run["observation_status"] in {"observed", "unobserved"},
                f"runs.{name} observation status is invalid")
        require(isinstance(run["reason"], str) and run["reason"], f"runs.{name} reason is empty")
        artifacts = _exact_keys(
            run["artifacts"], {"config", "hdd", "screenshots", "xiso"},
            f"runs.{name}.artifacts",
        )
        screenshots = _screenshots(artifacts["screenshots"], f"runs.{name}.screenshots")
        require(isinstance(run["outcomes"], list), f"runs.{name}.outcomes must be an array")

        if run["observation_status"] == "unobserved":
            require(artifacts["xiso"] is None and artifacts["config"] is None
                    and artifacts["hdd"] is None and not screenshots and not run["outcomes"],
                    f"runs.{name} unobserved state must contain no artifact placeholder or outcome")
        else:
            xiso = _artifact(artifacts["xiso"], f"runs.{name}.xiso")
            config = _artifact(artifacts["config"], f"runs.{name}.config")
            hdd = _artifact(artifacts["hdd"], f"runs.{name}.hdd")
            require(xiso["sha256"] == PROFILE[name]["xiso_sha256"]
                    and xiso["size"] == PROFILE[name]["xiso_size"],
                    f"runs.{name} XISO is outside the pinned pair")
            require(screenshots and run["outcomes"],
                    f"runs.{name} observed state needs screenshots and outcomes")
            kinds: list[str] = []
            roles = {row["role"] for row in screenshots}
            for raw_outcome in run["outcomes"]:
                kinds.append(_outcome(raw_outcome, name, roles)["kind"])
            require(kinds == sorted(kinds, key=OUTCOME_ORDER.index)
                    and len(kinds) == len(set(kinds)),
                    f"runs.{name} outcomes must be unique and canonical-order")
            if "target_visible" in kinds:
                require("boot_acceptance" in kinds,
                        f"runs.{name} target-visible outcome requires explicit boot acceptance")
            if verify_files:
                _verify_file(root, xiso, f"runs.{name}.xiso")
                _verify_file(root, config, f"runs.{name}.config")
                _verify_file(root, hdd, f"runs.{name}.hdd")
                for index, screenshot in enumerate(screenshots):
                    _verify_file(root, screenshot, f"runs.{name}.screenshots[{index}]")

        if pins is not None:
            require(name in pins, f"CLI pins omit {name}")
            expected = pins[name]
            require(expected["observation_status"] == run["observation_status"],
                    f"CLI {name} state differs")
            require(expected["outcomes"] == [row["kind"] for row in run["outcomes"]],
                    f"CLI {name} outcomes differ")
            require(expected["artifacts"] == artifacts, f"CLI {name} artifact pins differ")

    claims = _exact_keys(document["claims"], CLAIM_KEYS, "claims")
    require(all(type(value) is bool for value in claims.values()), "claims must all be booleans")
    derived = derive_claims(runs)
    require(claims == derived, "claims do not equal independently derived outcomes")
    require(document["status"] == derive_status(derived), "status does not equal derived outcome")
    return derived


def _role_map(values: list[str] | None, label: str, convert=lambda x: x) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in values or []:
        require("=" in raw, f"{label} must use role=value")
        role, value = raw.split("=", 1)
        require(role in SCREENSHOT_ROLES and role not in result, f"{label} role is invalid or duplicate")
        try:
            result[role] = convert(value)
        except (TypeError, ValueError) as exc:
            raise ResultError(f"{label} value is invalid") from exc
    return result


def _pins_from_args(args: argparse.Namespace, name: str) -> dict[str, Any]:
    state = getattr(args, f"{name}_state")
    outcomes = getattr(args, f"{name}_outcome") or []
    core = {}
    for kind in ("xiso", "config", "hdd"):
        path = getattr(args, f"{name}_{kind}_path")
        size = getattr(args, f"{name}_{kind}_size")
        digest = getattr(args, f"{name}_{kind}_sha256")
        values = (path, size, digest)
        require(all(value is None for value in values) or all(value is not None for value in values),
                f"CLI {name} {kind} path/size/hash must be supplied together")
        core[kind] = None if path is None else {
            "path": path,
            "sha256": digest,
            "size": size,
        }
    paths = _role_map(getattr(args, f"{name}_screenshot_path"), f"CLI {name} screenshot path")
    sizes = _role_map(getattr(args, f"{name}_screenshot_size"),
                      f"CLI {name} screenshot size", int)
    hashes = _role_map(getattr(args, f"{name}_screenshot_sha256"),
                       f"CLI {name} screenshot SHA-256")
    require(set(paths) == set(sizes) == set(hashes),
            f"CLI {name} screenshot path/size/hash role sets differ")
    screenshots = [
        {"path": paths[role], "role": role, "sha256": hashes[role], "size": sizes[role]}
        for role in sorted(paths)
    ]
    artifacts = {"config": core["config"], "hdd": core["hdd"],
                 "screenshots": screenshots, "xiso": core["xiso"]}
    if state == "unobserved":
        require(not outcomes and all(value is None for value in core.values()) and not screenshots,
                f"CLI {name} unobserved state forbids outcomes and artifact placeholders")
    else:
        require(outcomes and all(value is not None for value in core.values()) and screenshots,
                f"CLI {name} observed state requires outcomes and exact artifact pins")
    return {"artifacts": artifacts, "observation_status": state, "outcomes": outcomes}


def _add_run_args(parser: argparse.ArgumentParser, name: str, flag: str) -> None:
    parser.add_argument(f"--{flag}-state", choices=("observed", "unobserved"), required=True,
                        dest=f"{name}_state")
    parser.add_argument(f"--{flag}-outcome", choices=OUTCOME_ORDER, action="append",
                        dest=f"{name}_outcome")
    for kind in ("xiso", "config", "hdd"):
        parser.add_argument(f"--{flag}-{kind}-path", dest=f"{name}_{kind}_path")
        parser.add_argument(f"--{flag}-{kind}-size", type=int, dest=f"{name}_{kind}_size")
        parser.add_argument(f"--{flag}-{kind}-sha256", dest=f"{name}_{kind}_sha256")
    parser.add_argument(f"--{flag}-screenshot-path", action="append",
                        dest=f"{name}_screenshot_path", metavar="ROLE=PATH")
    parser.add_argument(f"--{flag}-screenshot-size", action="append",
                        dest=f"{name}_screenshot_size", metavar="ROLE=BYTES")
    parser.add_argument(f"--{flag}-screenshot-sha256", action="append",
                        dest=f"{name}_screenshot_sha256", metavar="ROLE=HEX")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--verify-files", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    _add_run_args(parser, "control", "control")
    _add_run_args(parser, "expanded_wall", "expanded")
    args = parser.parse_args()
    try:
        validate_schema_identity()
        pins = {
            "control": _pins_from_args(args, "control"),
            "expanded_wall": _pins_from_args(args, "expanded_wall"),
        }
        document = load_result(args.result)
        claims = validate_document(document, pins, verify_files=args.verify_files, root=args.root)
    except (OSError, ResultError) as exc:
        print(f"NFL_GROUP36_XEMU_RUNTIME_RESULT_REFUSED reason={exc}", file=sys.stderr)
        return 2
    print(
        "NFL_GROUP36_XEMU_RUNTIME_RESULT_PASS"
        f" status={document['status']}"
        f" boot={str(claims['xemu_boot_acceptance_proved']).lower()}"
        f" selector_skip={str(claims['s42_index18_quick_game_skip_observed']).lower()}"
        f" control_visible={str(claims['control_target_visible']).lower()}"
        f" expanded_visible={str(claims['expanded_target_visible']).lower()}"
        f" geometry_visible={str(claims['geometry_visibility_proved']).lower()}"
        " hardware=false production=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
