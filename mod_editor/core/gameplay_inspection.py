"""Hash-pinned, read-only gameplay and franchise inspection helpers.

The canonical research reports contain executable addresses for researchers.
This public-editor layer deliberately projects only named controls, proof
status, affected behavior, and safe next steps.  It never accepts or returns a
raw address and it never opens a game binary or save.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from .errors import ValidationError


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TUNING_REPORT = (
    ROOT / "reports/gameplay_tuning/gameplay_tuning_ai_draft_audit.json"
)
TUNING_REPORT_SIZE = 54_545
TUNING_REPORT_SHA256 = (
    "0c1c47c7f025f9fbb303b9a7d78e7aaf8e9d3c4d603a47bc7819d5ded43557ec"
)
TUNING_REPORT_SCHEMA = "vc_gameplay_tuning_ai_draft_audit/v1"

DEFAULT_FRANCHISE_REPORT = (
    ROOT / "reports/gameplay_tuning/nfl_franchise_limit_feasibility.json"
)
FRANCHISE_REPORT_SIZE = 17_707
FRANCHISE_REPORT_SHA256 = (
    "4d67e2d3009b7691a10eed4e1807371d3b80d6d0fafb5cb9cd62bcbf5cb8b4fd"
)
FRANCHISE_REPORT_SCHEMA = "nfl2k5_franchise_limit_feasibility/v1"

DEFAULT_NFL_SAVE_REPORT = (
    ROOT / "reports/gameplay_tuning/nfl2k5_xbox_save_inventory.json"
)
NFL_SAVE_REPORT_SIZE = 31_477
NFL_SAVE_REPORT_SHA256 = (
    "e49d30bc9adb87faf1a592a9d3a529169659be8f926be9db9028c90009477e3c"
)
NFL_SAVE_REPORT_SCHEMA = "nfl2k5_xbox_save_inventory/v1"

DEFAULT_PS2_FIXTURE_REPORT = (
    ROOT / "reports/gameplay_tuning/nfl2k5_ps2_fixture_availability.json"
)
PS2_FIXTURE_REPORT_SIZE = 6_581
PS2_FIXTURE_REPORT_SHA256 = (
    "f5fd78fecf5b4e3486a6aaed96b949b336507c3c3aa7ac9fed92b52d0074ee6b"
)
PS2_FIXTURE_REPORT_SCHEMA = "nfl2k5_ps2_fixture_audit/v1"

GAME_NAMES = {
    "nfl2k5": "ESPN NFL 2K5",
    "apf2k8": "All-Pro Football 2K8",
}
GAME_PLATFORMS = {"nfl2k5": "original Xbox", "apf2k8": "Xbox 360"}

FRANCHISE_TARGET_IDS = {
    "draft": "cpu_fantasy_draft_priority",
    "trade": "cpu_trade_evaluation",
    "salary-cap": "salary_cap_enforcement",
    "contracts": "contract_model_and_serialization",
    "super-bowl": "future_super_bowl_stadium_assignment",
}


def _read_pinned_report(
    path: Path,
    *,
    label: str,
    expected_size: int,
    expected_sha256: str,
    expected_schema: str,
) -> dict[str, Any]:
    """Read one immutable report without following links or racing identity."""

    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} report is missing: {path}") from exc
    if (
        not stat.S_ISREG(supplied.st_mode)
        or stat.S_ISLNK(supplied.st_mode)
        or supplied.st_nlink != 1
    ):
        raise ValidationError(
            f"{label} report must be a single-link non-symlink regular file"
        )

    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (supplied.st_dev, supplied.st_ino):
            raise ValidationError(f"{label} report identity changed while opening")
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ValidationError(f"{label} report link count or type changed")
        if opened.st_size != expected_size:
            raise ValidationError(f"{label} report size does not match the pinned audit")
        chunks: list[bytes] = []
        remaining = expected_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            if not block:
                raise ValidationError(f"{label} report ended early")
            chunks.append(block)
            remaining -= len(block)
        if os.read(descriptor, 1):
            raise ValidationError(f"{label} report grew while reading")
        after = os.fstat(descriptor)
        # ``opened`` and ``after`` are both os.fstat of this one descriptor.
        # Two fd stats agree on st_ctime_ns on every platform, Windows
        # included, so it stays in the fingerprint here and the
        # metadata-only-change signal is not lost on any platform.
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
            opened.st_nlink,
        ):
            raise ValidationError(f"{label} report changed while reading")
    finally:
        os.close(descriptor)

    payload = b"".join(chunks)
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValidationError(f"{label} report hash does not match the pinned audit")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{label} report is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != expected_schema:
        raise ValidationError(f"{label} report schema does not match")
    return value


def _tuning_report(path: Path) -> dict[str, Any]:
    return _read_pinned_report(
        path,
        label="Gameplay-tuning",
        expected_size=TUNING_REPORT_SIZE,
        expected_sha256=TUNING_REPORT_SHA256,
        expected_schema=TUNING_REPORT_SCHEMA,
    )


def _franchise_report(path: Path) -> dict[str, Any]:
    return _read_pinned_report(
        path,
        label="Franchise-limit",
        expected_size=FRANCHISE_REPORT_SIZE,
        expected_sha256=FRANCHISE_REPORT_SHA256,
        expected_schema=FRANCHISE_REPORT_SCHEMA,
    )


def _nfl_save_report(path: Path) -> dict[str, Any]:
    return _read_pinned_report(
        path,
        label="NFL-save inventory",
        expected_size=NFL_SAVE_REPORT_SIZE,
        expected_sha256=NFL_SAVE_REPORT_SHA256,
        expected_schema=NFL_SAVE_REPORT_SCHEMA,
    )


def _ps2_fixture_report(path: Path) -> dict[str, Any]:
    return _read_pinned_report(
        path,
        label="NFL-PS2 fixture",
        expected_size=PS2_FIXTURE_REPORT_SIZE,
        expected_sha256=PS2_FIXTURE_REPORT_SHA256,
        expected_schema=PS2_FIXTURE_REPORT_SCHEMA,
    )


def _report_provenance(
    path: Path, *, sha256: str, size: int, schema: str
) -> dict[str, Any]:
    try:
        display_path = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        display_path = path.resolve().as_posix()
    return {
        "path": display_path,
        "sha256": sha256,
        "size": size,
        "schema": schema,
    }


def _require_game(game: str) -> str:
    normalized = game.strip().lower()
    if normalized not in GAME_NAMES:
        raise ValidationError("Game must be the named id nfl2k5 or apf2k8")
    return normalized


def inspect_gameplay_sliders(
    game: str,
    report_path: Path = DEFAULT_TUNING_REPORT,
    nfl_save_report_path: Path = DEFAULT_NFL_SAVE_REPORT,
) -> dict[str, Any]:
    """Return the named 21-slider schema without storage/code addresses."""

    game_id = _require_game(game)
    report = _tuning_report(report_path)
    slider_node = report[game_id]["sliders"]
    source_rows = (
        slider_node["records"]
        if game_id == "nfl2k5"
        else slider_node["offline_records"]
    )
    labels = report["shared_slider_schema"]["labels"]
    if [row["label"] for row in source_rows] != labels:
        raise ValidationError("Pinned gameplay slider label order is inconsistent")

    public_rows: list[dict[str, Any]] = [
        {
            "index": row["index"],
            "name": row["label"],
            "named_menu_control_mapped": True,
            "current_profile_value_available": False,
        }
        for row in source_rows
    ]
    observed_save_report = None
    if game_id == "nfl2k5":
        save_report = _nfl_save_report(nfl_save_report_path)
        save_rows = {
            row["label"]: row for row in save_report["slider_snapshot"]["rows"]
        }
        if set(save_rows) != set(labels):
            raise ValidationError("Pinned NFL save slider labels are inconsistent")
        for row in public_rows:
            observed = save_rows[row["name"]]
            row["observed_settings1_value"] = observed["settings1"]
            row["observed_franchise1_value"] = observed["franchise1"]
        observed_save_report = _report_provenance(
            nfl_save_report_path,
            sha256=NFL_SAVE_REPORT_SHA256,
            size=NFL_SAVE_REPORT_SIZE,
            schema=NFL_SAVE_REPORT_SCHEMA,
        )
    platform_proof = (
        {
            "all_human_cpu_controls_reach_an_aggregate_consumer": True,
            "catching_named_setter_mapped": True,
            "final_catch_or_drop_branch_proved": False,
        }
        if game_id == "nfl2k5"
        else {
            "exact_serialized_value_count": 21,
            "exact_serialized_byte_count": 84,
            "offline_and_online_controls_share_callbacks_and_state": True,
            "catching_runtime_copy_mapped": True,
            "final_catch_or_drop_consumer_proved": False,
        }
    )
    summary = report["summary"]
    return {
        "schema": "mod_editor_gameplay_slider_inspection/v1",
        "game_id": game_id,
        "game": GAME_NAMES[game_id],
        "platform": GAME_PLATFORMS[game_id],
        "source_report": _report_provenance(
            report_path,
            sha256=TUNING_REPORT_SHA256,
            size=TUNING_REPORT_SIZE,
            schema=TUNING_REPORT_SCHEMA,
        ),
        "observed_save_report": observed_save_report,
        "access": "read-only definitions; no game binary or save opened",
        "slider_count": len(public_rows),
        "stock_ui_range": {
            "minimum": summary["stock_ui_minimum"],
            "maximum": summary["stock_ui_maximum"],
            "step": summary["stock_ui_step"],
        },
        "sliders": public_rows,
        "platform_proof": platform_proof,
        "current_values_available": False,
        "observed_fixture_values_available": game_id == "nfl2k5",
        "save_or_profile_writer_available": False,
        "executable_writer_available": False,
        "copy_only_archive_fix": False,
        "out_of_range_runtime_safety_proved": False,
        "warning": (
            "The names, stock range, and control ownership are mapped. NFL also "
            "shows values from one pinned Settings1/Franchise1 report; these are "
            "not live values from the user's current profile. No settings writer "
            "is available, and values outside the stock range are not proved safe."
        ),
    }


def inspect_nfl_save_inventory(
    report_path: Path = DEFAULT_NFL_SAVE_REPORT,
) -> dict[str, Any]:
    """Project mapped NFL save metadata without paths, hashes, or raw offsets."""

    report = _nfl_save_report(report_path)
    snapshot = report["slider_snapshot"]
    by_name = {row["label"]: row for row in snapshot["rows"]}
    if set(by_name) != set(snapshot["semantic_order"]):
        raise ValidationError("Pinned NFL save slider rows are inconsistent")
    containers = []
    for row in report["containers"]:
        files = row["files"]
        containers.append(
            {
                "display_name": row["display_name"],
                "type": row["type"],
                "savegame_size": files["SAVEGAME.DAT"]["file_size"],
                "extra_size": files["EXTRA"]["file_size"],
            }
        )
    return {
        "schema": "mod_editor_nfl_save_inventory_inspection/v1",
        "game_id": "nfl2k5",
        "game": GAME_NAMES["nfl2k5"],
        "platform": GAME_PLATFORMS["nfl2k5"],
        "source_report": _report_provenance(
            report_path,
            sha256=NFL_SAVE_REPORT_SHA256,
            size=NFL_SAVE_REPORT_SIZE,
            schema=NFL_SAVE_REPORT_SCHEMA,
        ),
        "access": "sanitized read-only evidence; no HDD image or save opened",
        "title_id": report["summary"]["title_id"],
        "container_count": len(containers),
        "containers": containers,
        "observed_slider_values": [
            {
                "name": name,
                "settings1": by_name[name]["settings1"],
                "franchise1": by_name[name]["franchise1"],
            }
            for name in snapshot["semantic_order"]
        ],
        "integrity_boundary": {
            "savegame_signature_owned": report["summary"][
                "signature_owner_proved"
            ],
            "signature_mode": report["executable_evidence"]["signature_owner"][
                "begin"
            ]["XCalculateSignatureBegin_mode"],
            "extra_size": report["executable_evidence"]["signature_owner"][
                "write_close"
            ]["writes_EXTRA_size"],
            "platform_keys_read_or_emitted": report["scope"][
                "platform_keys_read_or_emitted"
            ],
            "safe_writer_available": report["summary"]["safe_writer_proved"],
        },
        "warning": (
            "This is a metadata-only snapshot of observed saves. Editing requires "
            "one-variable serializer proof, platform-backed signing, a copied HDD, "
            "and an independent clean game reload."
        ),
    }


def inspect_draft_priority(
    game: str, report_path: Path = DEFAULT_TUNING_REPORT
) -> dict[str, Any]:
    """Return named position weights and their title-specific proof status."""

    game_id = _require_game(game)
    report = _tuning_report(report_path)
    if game_id == "nfl2k5":
        draft = report[game_id]["cpu_fantasy_draft"]
        rows = draft["priority_table"]["rows"]
        status = {
            "table_copy_count": 1,
            "cpu_selector_owner_proved": True,
            "ranking_algorithm_proved": True,
            "classification": "exact Xbox executable-patch candidate",
        }
        warning = (
            "These are live Xbox CPU fantasy-draft priorities, but changing them "
            "crosses signed-executable integrity and has no released writer or "
            "deterministic runtime trial."
        )
    else:
        lineage = report[game_id]["fantasy_draft_lineage"]
        tables = lineage["priority_tables"]
        if len(tables) != 2 or tables[0]["rows"] != tables[1]["rows"]:
            raise ValidationError("Pinned APF draft-table copies are inconsistent")
        rows = tables[0]["rows"]
        status = {
            "table_copy_count": len(tables),
            "cpu_selector_owner_proved": lineage["cpu_selector_proved"],
            "ranking_algorithm_proved": False,
            "classification": "retained lineage; live APF control not proved",
        }
        warning = (
            "The two APF table copies match NFL's weights, but no live APF CPU "
            "selector owns them. They must not be presented as an effective "
            "draft-AI control."
        )

    return {
        "schema": "mod_editor_draft_priority_inspection/v1",
        "game_id": game_id,
        "game": GAME_NAMES[game_id],
        "platform": GAME_PLATFORMS[game_id],
        "source_report": _report_provenance(
            report_path,
            sha256=TUNING_REPORT_SHA256,
            size=TUNING_REPORT_SIZE,
            schema=TUNING_REPORT_SCHEMA,
        ),
        "access": "read-only constants; no game binary or save opened",
        "position_weight_count": len(rows),
        "position_weights": [
            {
                "position_code": row["position_code"],
                "position": row["position"],
                "weight": row["weight"],
            }
            for row in rows
        ],
        "proof_status": status,
        "copy_only_archive_fix": False,
        "safe_writer_available": False,
        "runtime_patch_performed": False,
        "warning": warning,
    }


def _franchise_public_evidence(row: dict[str, Any]) -> dict[str, Any]:
    row_id = row["id"]
    proof = row["proof"]
    if row_id == "cpu_fantasy_draft_priority":
        return {
            "position_weight_count": proof["weight_count"],
            "static_ranking_algorithm_owned": True,
            "deterministic_runtime_trial_complete": False,
        }
    if row_id == "cpu_trade_evaluation":
        return {
            "trade_feature_present": proof["trade_feature_present"],
            "cpu_offer_or_acceptance_evaluator_owned": proof[
                "cpu_acceptance_or_offer_scoring_function_proved"
            ],
            "trade_save_records_mapped": proof["trade_save_records_mapped"],
        }
    if row_id == "salary_cap_enforcement":
        return {
            "season_entry_validator_owned": True,
            "runtime_team_total_comparison_owned": True,
            "maximum_roster_count_allowed_by_gate": 54,
            "annual_cap_growth_formula_proved": proof[
                "annual_cap_growth_formula_proved"
            ],
            "save_field_encoding_proved": False,
        }
    if row_id == "contract_model_and_serialization":
        return {
            "contract_screens_present": True,
            "dynamic_contract_fields_proved": False,
            "save_container_mapped": proof["dashboard_save_container_mapped"],
            "disc_roster_fields_are_franchise_fields": proof[
                "disc_roster_contract_fields_promoted"
            ],
        }
    if row_id == "future_super_bowl_stadium_assignment":
        mapping = [
            {
                "season_index": item["season_index"],
                "stadium_name": item["display_name"],
                "location": item["location"],
            }
            for item in proof["season_index_mapping"]
        ]
        default = proof["default_mapping"]
        return {
            "year_to_venue_selector_owned": proof[
                "year_to_venue_mapping_proved"
            ],
            "franchise_super_bowl_week_owned": True,
            "season_zero_through_four": mapping,
            "season_five_and_later": {
                "stadium_name": default["display_name"],
                "location": default["location"],
                "all_later_seasons_collapse_here": proof[
                    "all_season_indices_at_or_above_5_collapse_to_s45"
                ],
            },
            "year_five_or_six_runtime_reproduction_complete": proof[
                "five_year_failure_reproduced_in_this_workspace"
            ],
        }
    raise ValidationError(f"Unsupported franchise row in pinned report: {row_id}")


def _franchise_requirements(row_id: str) -> list[str]:
    return {
        "cpu_fantasy_draft_priority": [
            "authorized copied-executable or emulator-memory experiment",
            "independent executable-integrity verification",
            "seeded before/after CPU draft comparison",
            "separate PS2 executable ownership for PCSX2",
        ],
        "cpu_trade_evaluation": [
            "controlled franchise save",
            "CPU-generated offer trace through final accept or decline",
            "field-level valuation ownership and deterministic oracle",
            "separate PS2 executable ownership for PCSX2",
        ],
        "salary_cap_enforcement": [
            "one-variable contract save pair",
            "season-boundary save pair",
            "cap units, growth, penalties, and exceptions mapping",
            "separate PS2 executable ownership for PCSX2",
        ],
        "contract_model_and_serialization": [
            "same-season one-contract before/after saves",
            "next-season progression save",
            "field encoding, integrity, and load precedence proof",
            "CPU negotiation and re-signing ownership",
        ],
        "future_super_bowl_stadium_assignment": [
            "chosen post-season-four venue policy",
            "year-five and year-six controlled runtime reproduction",
            "authorized copied-executable integrity handling",
            "separate PS2 executable ownership for PCSX2",
        ],
    }[row_id]


def _public_franchise_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_limitation": row["user_limitation"],
        "feasibility": row["feasibility"],
        "current_proof": row["current_proof"],
        "likely_mutation_layer": row["likely_mutation_layer"],
        "named_evidence": _franchise_public_evidence(row),
        "archive_only_fix": row["archive_only_fix"],
        "current_writer_safe": row["current_writer_safe"],
        "requirements_before_write": _franchise_requirements(row["id"]),
    }


def inspect_nfl_franchise_limit(
    target: str,
    report_path: Path = DEFAULT_FRANCHISE_REPORT,
    ps2_fixture_report_path: Path = DEFAULT_PS2_FIXTURE_REPORT,
) -> dict[str, Any]:
    """Inspect one named franchise limit, or the complete five-row matrix."""

    normalized = target.strip().lower()
    if normalized != "all" and normalized not in FRANCHISE_TARGET_IDS:
        choices = ", ".join([*FRANCHISE_TARGET_IDS, "all"])
        raise ValidationError(f"Franchise target must be one of: {choices}")
    report = _franchise_report(report_path)
    ps2_report = _ps2_fixture_report(ps2_fixture_report_path)
    by_id = {row["id"]: row for row in report["matrix"]}
    if set(by_id) != set(FRANCHISE_TARGET_IDS.values()):
        raise ValidationError("Pinned franchise matrix does not contain the expected rows")

    provenance = _report_provenance(
        report_path,
        sha256=FRANCHISE_REPORT_SHA256,
        size=FRANCHISE_REPORT_SIZE,
        schema=FRANCHISE_REPORT_SCHEMA,
    )
    ps2_provenance = _report_provenance(
        ps2_fixture_report_path,
        sha256=PS2_FIXTURE_REPORT_SHA256,
        size=PS2_FIXTURE_REPORT_SIZE,
        schema=PS2_FIXTURE_REPORT_SCHEMA,
    )
    ps2_summary = ps2_report["summary"]
    ps2_limitations = [
        {
            "id": row["id"],
            "owner_status": row["ps2_owner_status"],
            "safe_patch_ready": row["safe_ps2_patch_ready"],
            "xbox_address_reuse_allowed": row["address_reuse_from_xbox_allowed"],
            "required_evidence": row["required_ps2_evidence"],
        }
        for row in ps2_report["limitations"]
    ]
    common = {
        "game_id": "nfl2k5",
        "game": GAME_NAMES["nfl2k5"],
        "platform": GAME_PLATFORMS["nfl2k5"],
        "source_report": provenance,
        "pcsx2_fixture_report": ps2_provenance,
        "access": "read-only feasibility evidence; no game binary or save opened",
        "safe_writer_count": report["summary"]["current_safe_writer_count"],
        "archive_only_fix_count": report["summary"]["archive_only_fix_count"],
        "pcsx2_patch_coordinates_available": False,
        "pcsx2_target": {
            "serial": ps2_report["target"]["serial"],
            "disc_version": ps2_report["target"]["disc_version"],
            "boot_elf_expected_name": ps2_report["target"][
                "boot_elf_expected_name"
            ],
            "expected_iso_size": ps2_report["target"]["expected_iso_size"],
            "expected_iso_md5": ps2_report["target"]["expected_iso_md5"],
        },
        "pcsx2_local_fixture_status": {
            "expected_iso_present": ps2_summary["expected_iso_present"],
            "boot_elf_present": ps2_summary["extracted_boot_elf_present"],
            "save_marker_present": ps2_summary["save_directory_marker_present"],
            "texture_dump_present": ps2_summary["pcsx2_texture_dump_present"],
            "safe_patch_ready": ps2_summary["safe_ps2_patch_ready"],
        },
        "pcsx2_limitation_status": ps2_limitations,
        "warning": report["platform_boundary"]["conclusion"],
    }
    if normalized == "all":
        return {
            "schema": "mod_editor_nfl_franchise_matrix_inspection/v1",
            **common,
            "target_count": len(FRANCHISE_TARGET_IDS),
            "targets": [
                _public_franchise_row(by_id[row_id])
                for row_id in FRANCHISE_TARGET_IDS.values()
            ],
        }
    row_id = FRANCHISE_TARGET_IDS[normalized]
    return {
        "schema": "mod_editor_nfl_franchise_limit_inspection/v1",
        **common,
        "target_name": normalized,
        "target": _public_franchise_row(by_id[row_id]),
    }


__all__ = [
    "inspect_draft_priority",
    "inspect_gameplay_sliders",
    "inspect_nfl_franchise_limit",
    "inspect_nfl_save_inventory",
]
