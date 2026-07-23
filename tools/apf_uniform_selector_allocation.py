#!/usr/bin/env python3
"""Plan maximum APF 2K8 per-team uniform selector isolation.

This is a read-only capacity and recipe-planning tool.  It consumes the exact
hash-pinned retail uniform inventory, proves that both neutral selector banks
agree on byte 0 for every filename-owned family, and computes deterministic
maximum-distinct, minimum-change assignments.  It never edits ROST, an
archive volume, or a game executable.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "reports/assets/apf_uniform_inventory.json"
INVENTORY_SIZE = 4_350_600
INVENTORY_SHA256 = "b3ad0e44af0163b30857e20c7c4e90ceb89cbc3dbc8cc41508fce3aaf1c136c7"
INVENTORY_SCHEMA = "apf_uniform_inventory/v1"
ALLOCATION_SPEC = ROOT / "reports/specs/apf2k8_uniform_selector_allocation.v1.json"
ALLOCATION_SPEC_SIZE = 8_554
ALLOCATION_SPEC_SHA256 = "0eff80d01c04fbfbfc294d4125d203389c8a6cff4bcbab0ac20a227c58d6b05c"
ALLOCATION_SPEC_SCHEMA = "apf2k8_uniform_selector_allocation_spec/v1"
SCHEMA = "apf2k8_uniform_selector_allocation/v1"

TEAM_COUNT = 40
BUILT_IN_COUNT = 24
BANK_COUNT = 2
SLOTS_PER_BANK = 14
SELECTOR_TABLE_OFFSET = 0x1E0228
SELECTOR_TABLE_COUNT = 3_724
SELECTOR_STRIDE = 8

# A selector slot is the ownership unit.  Shoulder color and normal packages
# deliberately share slot 11 and therefore receive one allocation plan.
EXPECTED_SLOT_FAMILIES: dict[int, tuple[str, ...]] = {
    2: ("glove",),
    3: ("helmet",),
    4: ("jersey",),
    5: ("logo",),
    6: ("textlogo",),
    7: ("font",),
    8: ("number",),
    9: ("pants",),
    10: ("shoe",),
    11: ("shoulder", "shoulder_normal"),
    12: ("sock",),
}
EXPECTED_SLOT_KINDS = (
    (0, BUILT_IN_COUNT, "built_in_team"),
    (BUILT_IN_COUNT, 32, "online_slot"),
    (32, TEAM_COUNT, "user_slot"),
)


class AllocationError(ValueError):
    """The pinned inventory or requested allocation contract failed."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def canonical_pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_json_object(raw: bytes, what: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise AllocationError(f"{what} contains forbidden constant {value!r}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AllocationError(f"{what} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AllocationError(f"{what} is not strict JSON") from exc
    if not isinstance(value, dict) or canonical_pretty_json_bytes(value) != raw:
        raise AllocationError(f"{what} is not canonical sorted object JSON")
    return value


def load_inventory(path: Path) -> tuple[dict[str, Any], bytes]:
    """Load only an exact byte copy of the frozen retail inventory."""

    raw = path.read_bytes()
    if len(raw) != INVENTORY_SIZE or sha256_bytes(raw) != INVENTORY_SHA256:
        raise AllocationError("pinned APF uniform inventory identity drift")
    value = _strict_json_object(raw, "APF uniform inventory")
    if value.get("schema") != INVENTORY_SCHEMA:
        raise AllocationError("unsupported APF uniform inventory schema")
    return value, raw


def load_allocation_spec() -> tuple[dict[str, Any], bytes]:
    raw = ALLOCATION_SPEC.read_bytes()
    if len(raw) != ALLOCATION_SPEC_SIZE or sha256_bytes(raw) != ALLOCATION_SPEC_SHA256:
        raise AllocationError("pinned APF selector allocation specification identity drift")
    value = _strict_json_object(raw, "APF selector allocation specification")
    if value.get("schema") != ALLOCATION_SPEC_SCHEMA:
        raise AllocationError("unsupported APF selector allocation specification schema")
    return value, raw


def _integer(value: Any, what: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AllocationError(f"{what} is not an integer")
    if not minimum <= value <= maximum:
        raise AllocationError(f"{what} is outside {minimum}..{maximum}")
    return value


def family_groups(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate and coalesce catalog families that share one selector slot."""

    rows = inventory.get("family_specs")
    if not isinstance(rows, list):
        raise AllocationError("family_specs is missing")
    by_name: dict[str, dict[str, Any]] = {}
    by_slot: dict[int, list[dict[str, Any]]] = {}
    for ordinal, row in enumerate(rows):
        if not isinstance(row, dict):
            raise AllocationError(f"family spec {ordinal} is not an object")
        name = row.get("family")
        if not isinstance(name, str) or not name:
            raise AllocationError(f"family spec {ordinal} has an invalid name")
        if name in by_name:
            raise AllocationError(f"duplicate family spec {name!r}")
        slot = _integer(row.get("selector_slot"), f"family {name} slot", 0, 13)
        _integer(row.get("catalog_count"), f"family {name} catalog count", 1, 256)
        by_name[name] = row
        by_slot.setdefault(slot, []).append(row)

    actual = {
        slot: tuple(sorted(str(row["family"]) for row in grouped))
        for slot, grouped in by_slot.items()
    }
    if actual != EXPECTED_SLOT_FAMILIES:
        raise AllocationError("filename-owned selector family/slot grouping drift")

    result: list[dict[str, Any]] = []
    for slot, expected_names in sorted(EXPECTED_SLOT_FAMILIES.items()):
        grouped = by_slot[slot]
        counts = {int(row["catalog_count"]) for row in grouped}
        references = {
            tuple(row.get("referenced_asset_indices", [])) for row in grouped
        }
        if len(counts) != 1 or len(references) != 1:
            raise AllocationError(f"slot {slot} paired-family catalog contract drift")
        result.append({
            "catalog_count": counts.pop(),
            "family": expected_names[0],
            "physical_families": list(expected_names),
            "selector_slot": slot,
            "spec_referenced_asset_indices": list(references.pop()),
        })
    return result


def _expected_slot_kind(team_index: int) -> str:
    for start, end, kind in EXPECTED_SLOT_KINDS:
        if start <= team_index < end:
            return kind
    raise AllocationError("team index is outside the frozen slot-kind ranges")


def teams(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the complete 40 x 2 x 14 pointer-derived selector graph."""

    source = inventory.get("source")
    roster = source.get("roster") if isinstance(source, dict) else None
    required_roster = {
        "decoded_length": 2_294_304,
        "decoded_sha256": "e959d3067ebcdbeb4f08979fa74d9fa61cf90fd91b90793863e6a3313be7f7ff",
        "outer_stored_sha256": "e98dd07b38caa73ea2ce91eed19bef68896f9b63830a9169af4b7f22d8788cc7",
        "outer_stored_size": 436_224,
        "outer_table_index": 1_126,
        "referenced_selector_record_count": 1_120,
        "selector_record_count": SELECTOR_TABLE_COUNT,
        "selector_record_stride": "0x08",
        "selector_table_index": 17,
        "selector_table_offset": "0x1e0228",
        "team_count": TEAM_COUNT,
    }
    if not isinstance(roster, dict) or any(
        roster.get(key) != expected for key, expected in required_roster.items()
    ):
        raise AllocationError("pinned roster selector source contract drift")

    graph = inventory.get("team_selector_graph")
    rows = graph.get("teams") if isinstance(graph, dict) else None
    if not isinstance(rows, list) or len(rows) != TEAM_COUNT:
        raise AllocationError("selector graph does not contain exactly 40 teams")

    seen_indices: set[int] = set()
    seen_offsets: set[str] = set()
    for expected_team, team in enumerate(rows):
        if not isinstance(team, dict) or team.get("team_index") != expected_team:
            raise AllocationError("team order/index drift")
        if team.get("slot_kind") != _expected_slot_kind(expected_team):
            raise AllocationError(f"team {expected_team} slot kind drift")
        if not isinstance(team.get("display_name"), str) or not isinstance(
            team.get("abbreviation"), str
        ):
            raise AllocationError(f"team {expected_team} identity is invalid")
        banks = team.get("banks")
        if not isinstance(banks, list) or len(banks) != BANK_COUNT:
            raise AllocationError(f"team {expected_team} does not have two banks")
        for expected_bank, bank in enumerate(banks):
            if not isinstance(bank, dict) or bank.get("bank") != expected_bank:
                raise AllocationError(f"team {expected_team} bank order drift")
            selectors = bank.get("selectors")
            if not isinstance(selectors, list) or len(selectors) != SLOTS_PER_BANK:
                raise AllocationError(
                    f"team {expected_team} bank {expected_bank} selector count drift"
                )
            if [row.get("slot") if isinstance(row, dict) else None for row in selectors] != list(
                range(SLOTS_PER_BANK)
            ):
                raise AllocationError(
                    f"team {expected_team} bank {expected_bank} slot order drift"
                )
            for selector in selectors:
                assert isinstance(selector, dict)
                slot = int(selector["slot"])
                index = _integer(
                    selector.get("selector_record_index"),
                    "selector record index",
                    0,
                    SELECTOR_TABLE_COUNT - 1,
                )
                offset = selector.get("selector_record_offset")
                expected_offset = f"0x{SELECTOR_TABLE_OFFSET + index * SELECTOR_STRIDE:x}"
                if offset != expected_offset or index in seen_indices or offset in seen_offsets:
                    raise AllocationError("selector record ownership is invalid or aliased")
                seen_indices.add(index)
                seen_offsets.add(offset)

                raw_hex = selector.get("raw_record_hex")
                opaque_hex = selector.get("opaque_bytes_1_7_hex")
                asset = selector.get("asset_index_byte_0")
                if (
                    not isinstance(raw_hex, str)
                    or len(raw_hex) != 16
                    or not isinstance(opaque_hex, str)
                    or len(opaque_hex) != 14
                    or isinstance(asset, bool)
                    or not isinstance(asset, int)
                ):
                    raise AllocationError("selector record byte fields are invalid")
                try:
                    raw = bytes.fromhex(raw_hex)
                    opaque = bytes.fromhex(opaque_hex)
                except ValueError as exc:
                    raise AllocationError("selector record contains invalid hex") from exc
                if raw[0] != asset or raw[1:] != opaque:
                    raise AllocationError("selector record byte fields disagree")

                expected_families = list(EXPECTED_SLOT_FAMILIES.get(slot, ()))
                if selector.get("families") != expected_families:
                    raise AllocationError(f"selector slot {slot} family ownership drift")
                if expected_families and not str(selector.get("semantic_status", "")).startswith(
                    "filename selector proved"
                ):
                    raise AllocationError(f"selector slot {slot} filename ownership is unproved")

    if len(seen_indices) != TEAM_COUNT * BANK_COUNT * SLOTS_PER_BANK:
        raise AllocationError("selector graph record cardinality drift")
    return rows


def selector_vector(
    team_rows: list[dict[str, Any]],
    slot: int,
    catalog_count: int,
) -> tuple[list[int], list[dict[str, Any]]]:
    """Derive one value per team and retain both neutral-bank authorities."""

    values: list[int] = []
    evidence: list[dict[str, Any]] = []
    selected_indices: set[int] = set()
    for expected_team, team in enumerate(team_rows):
        selected: list[dict[str, Any]] = []
        for expected_bank, bank in enumerate(team["banks"]):
            matches = [row for row in bank["selectors"] if row["slot"] == slot]
            if len(matches) != 1:
                raise AllocationError(
                    f"team {expected_team} bank {expected_bank} slot {slot} is not unique"
                )
            row = matches[0]
            asset = _integer(
                row.get("asset_index_byte_0"),
                f"team {expected_team} bank {expected_bank} slot {slot} asset",
                0,
                catalog_count - 1,
            )
            index = int(row["selector_record_index"])
            if index in selected_indices:
                raise AllocationError("selected family records are aliased")
            selected_indices.add(index)
            selected.append(row)
        bank_values = [int(row["asset_index_byte_0"]) for row in selected]
        if bank_values[0] != bank_values[1]:
            raise AllocationError(
                f"team {expected_team} slot {slot} differs between neutral banks"
            )
        values.append(bank_values[0])
        evidence.append({
            "abbreviation": team["abbreviation"],
            "bank_selector_records": [
                {
                    "bank": bank,
                    "opaque_bytes_1_7_hex": selected[bank]["opaque_bytes_1_7_hex"],
                    "selector_record_index": selected[bank]["selector_record_index"],
                    "selector_record_offset": selected[bank]["selector_record_offset"],
                }
                for bank in range(BANK_COUNT)
            ],
            "display_name": team["display_name"],
            "retail_asset_index": bank_values[0],
            "slot_kind": team["slot_kind"],
            "team_index": expected_team,
        })
    if len(selected_indices) != TEAM_COUNT * BANK_COUNT:
        raise AllocationError("selected family record cardinality drift")
    return values, evidence


def maximum_isolation_plan(
    retail: list[int],
    catalog_count: int,
    scope_count: int,
) -> dict[str, Any]:
    """Maximize distinct identities, then minimize writes deterministically.

    The upper bound is ``min(scope_count, catalog_count)``.  Every new
    identity requires at least one changed team.  We retain the first retail
    owner of each identity, then give the earliest duplicate teams the lowest
    catalog indices absent from the original scope until the upper bound is
    reached.  This achieves both the capacity bound and the minimum possible
    number of changed team assignments.
    """

    if len(retail) != TEAM_COUNT or not 1 <= scope_count <= TEAM_COUNT:
        raise AllocationError("allocation scope is invalid")
    if not 1 <= catalog_count <= 256 or any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value < catalog_count
        for value in retail
    ):
        raise AllocationError("allocation retail vector/catalog is invalid")

    wanted = list(retail[:scope_count])
    original_assets = set(wanted)
    upper_bound = min(scope_count, catalog_count)
    required_new_identities = upper_bound - len(original_assets)
    missing_assets = [asset for asset in range(catalog_count) if asset not in original_assets]

    first_owners: set[int] = set()
    duplicate_team_indices: list[int] = []
    for team_index, asset in enumerate(wanted):
        if asset in first_owners:
            duplicate_team_indices.append(team_index)
        else:
            first_owners.add(asset)
    if len(duplicate_team_indices) < required_new_identities or len(missing_assets) < required_new_identities:
        raise AllocationError("allocation proof does not have enough duplicate/missing identities")

    assignments = list(wanted)
    changed_team_indices = duplicate_team_indices[:required_new_identities]
    for team_index, replacement in zip(
        changed_team_indices,
        missing_assets[:required_new_identities],
    ):
        assignments[team_index] = replacement

    distinct_after = len(set(assignments))
    actual_changed = [
        team_index
        for team_index, (before, after) in enumerate(zip(wanted, assignments))
        if before != after
    ]
    if distinct_after != upper_bound or actual_changed != changed_team_indices:
        raise AllocationError("deterministic allocation did not meet its proof objective")

    return {
        "all_catalog_assets_used_after": set(assignments) == set(range(catalog_count)),
        "assignment_vector": assignments,
        "assignments": [
            {
                "changed": before != after,
                "expected_retail_asset_index": before,
                "replacement_asset_index": after,
                "team_index": team_index,
            }
            for team_index, (before, after) in enumerate(zip(wanted, assignments))
        ],
        "catalog_capacity_upper_bound": upper_bound,
        "changed_selector_byte_count_both_banks": len(actual_changed) * BANK_COUNT,
        "changed_team_count": len(actual_changed),
        "changed_team_indices": actual_changed,
        "complete_scope_internal_isolation_possible": distinct_after == scope_count,
        "distinct_asset_count_after": distinct_after,
        "distinct_asset_count_before": len(original_assets),
        "minimum_changed_team_count_for_upper_bound": required_new_identities,
        "scope_team_count": scope_count,
        "unavoidable_excess_team_count": scope_count - upper_bound,
        "unused_catalog_asset_indices_after": sorted(set(range(catalog_count)) - set(assignments)),
    }


def _outside_scope_boundary(
    plan: dict[str, Any],
    retail: list[int],
) -> dict[str, Any]:
    scope_count = int(plan["scope_team_count"])
    outside_assets = set(retail[scope_count:])
    shared_assets = sorted(set(plan["assignment_vector"]) & outside_assets)
    scope_teams = [
        index
        for index, asset in enumerate(plan["assignment_vector"])
        if asset in outside_assets
    ]
    return {
        "asset_indices_shared_with_unchanged_outside_scope": shared_assets,
        "outside_scope_team_count": TEAM_COUNT - scope_count,
        "scope_team_indices_sharing_with_unchanged_outside_scope": scope_teams,
    }


def build_report(inventory: dict[str, Any], raw: bytes) -> dict[str, Any]:
    _, spec_raw = load_allocation_spec()
    grouped = family_groups(inventory)
    team_rows = teams(inventory)
    results: list[dict[str, Any]] = []
    for group in grouped:
        slot = int(group["selector_slot"])
        catalog_count = int(group["catalog_count"])
        retail, evidence = selector_vector(team_rows, slot, catalog_count)
        referenced = sorted(set(retail))
        if referenced != group["spec_referenced_asset_indices"]:
            raise AllocationError(f"slot {slot} referenced-asset summary drift")
        built_in = maximum_isolation_plan(retail, catalog_count, BUILT_IN_COUNT)
        all_teams = maximum_isolation_plan(retail, catalog_count, TEAM_COUNT)
        built_in["outside_scope_boundary"] = _outside_scope_boundary(built_in, retail)
        all_teams["outside_scope_boundary"] = _outside_scope_boundary(all_teams, retail)
        results.append({
            "all_team_plan": all_teams,
            "built_in_plan": built_in,
            "catalog_count": catalog_count,
            "family": group["family"],
            "physical_families": group["physical_families"],
            "retail": {
                "all_team_asset_use_counts": {
                    str(key): value for key, value in sorted(Counter(retail).items())
                },
                "bank_byte_0_equal_for_every_team": True,
                "built_in_asset_use_counts": {
                    str(key): value
                    for key, value in sorted(Counter(retail[:BUILT_IN_COUNT]).items())
                },
                "referenced_asset_indices": referenced,
                "selector_evidence": evidence,
                "selector_vector": retail,
                "unreferenced_catalog_asset_indices": sorted(
                    set(range(catalog_count)) - set(retail)
                ),
            },
            "selector_slot": slot,
            "writer_boundary": {
                "existing_fail_closed_selector_writer": (
                    "tools/apf_jersey_selector_patch.py"
                    if group["family"] == "jersey"
                    else None
                ),
                "existing_independent_selector_verifier": (
                    "tools/apf_jersey_selector_verify.py"
                    if group["family"] == "jersey"
                    else None
                ),
                "plan_is_write_authority": False,
                "runtime_visibility_proved": False,
            },
        })

    built_in_changes = sum(row["built_in_plan"]["changed_team_count"] for row in results)
    all_team_changes = sum(row["all_team_plan"]["changed_team_count"] for row in results)
    return {
        "claim_boundary": {
            "archive_or_executable_growth_performed": False,
            "bank_zero_or_one_named_home_or_away": False,
            "capacity_plan_authorizes_non_jersey_writer": False,
            "compression_fit_evaluated_by_this_report": False,
            "offline_selector_capacity_only": True,
            "opaque_selector_bytes_1_through_7_interpreted": False,
            "roster_or_game_volume_written": False,
            "runtime_visibility_proved": False,
        },
        "combined_plans": {
            "all_40": {
                "changed_selector_byte_count_both_banks": all_team_changes * BANK_COUNT,
                "changed_team_family_assignment_count": all_team_changes,
                "component_family_plan_count": len(results),
            },
            "built_in_24": {
                "changed_selector_byte_count_both_banks": built_in_changes * BANK_COUNT,
                "changed_team_family_assignment_count": built_in_changes,
                "component_family_plan_count": len(results),
            },
        },
        "families": results,
        "schema": SCHEMA,
        "source": {
            "allocation_spec_path": str(ALLOCATION_SPEC.relative_to(ROOT)),
            "allocation_spec_sha256": sha256_bytes(spec_raw),
            "allocation_spec_size_bytes": len(spec_raw),
            "decoded_roster_sha256": inventory["source"]["roster"]["decoded_sha256"],
            "inventory_sha256": sha256_bytes(raw),
            "inventory_size_bytes": len(raw),
            "path": str(DEFAULT_INVENTORY.relative_to(ROOT)),
        },
        "summary": {
            "all_40_scope_internally_isolatable_families": [
                row["family"]
                for row in results
                if row["all_team_plan"]["complete_scope_internal_isolation_possible"]
            ],
            "built_in_24_scope_internally_isolatable_families": [
                row["family"]
                for row in results
                if row["built_in_plan"]["complete_scope_internal_isolation_possible"]
            ],
            "canonical_selector_family_count": len(results),
            "filename_owned_selector_slot_count": len(results),
            "physical_catalog_family_count": sum(len(row["physical_families"]) for row in results),
            "two_bank_selector_record_count_covered": len(results) * TEAM_COUNT * BANK_COUNT,
        },
        "teams": [
            {
                "abbreviation": team["abbreviation"],
                "display_name": team["display_name"],
                "slot_kind": team["slot_kind"],
                "team_index": team["team_index"],
            }
            for team in team_rows
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
        help="exact byte copy of the pinned APF uniform inventory",
    )
    parser.add_argument("--json", type=Path, help="write canonical report to a new path")
    args = parser.parse_args(argv)
    try:
        inventory, raw = load_inventory(args.inventory)
        report = build_report(inventory, raw)
        payload = canonical_json_bytes(report)
        if args.json is not None:
            with args.json.open("xb") as descriptor:
                descriptor.write(payload)
        print(payload.decode("utf-8"), end="")
    except (AllocationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
