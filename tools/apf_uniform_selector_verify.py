#!/usr/bin/env python3
"""Independently verify the APF 2K8 built-in all-family selector writer.

This verifier imports no writer or project archive/ROST implementation. It
uses the standard-library-only retail parser from the separately implemented
jersey verifier, then independently validates the family-aware recipe,
re-derives all 1120 selector targets, reconstructs the wanted decoded ROST,
re-encodes H7A, rebuilds IFF/footer/tail, reconstructs the complete manifest,
and compares the copied volume outside the one fixed outer entry.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any

import apf_jersey_selector_verify as base


ROOT = Path(__file__).resolve().parents[1]
ALLOCATION_REPORT = ROOT / "reports/assets/apf_uniform_selector_allocation.json"
ALLOCATION_REPORT_SIZE = 264_669
ALLOCATION_REPORT_SHA256 = "389efe3a90839bcc2210df6292817920b7bbfa1f2c0389ee632b2915adcdbef6"
CAPACITY_REPORT = ROOT / "reports/assets/apf_uniform_selector_capacity_probe.json"
CAPACITY_REPORT_SIZE = 18_842
CAPACITY_REPORT_SHA256 = "4180997cc63129ef2df0f31a392abe270431ed490551db382ca4d91686e96213"
RECIPE_SCHEMA_FILE = ROOT / "reports/specs/apf2k8_uniform_selector_assignment_recipe.schema.json"
RECIPE_SCHEMA_FILE_SIZE = 6_196
RECIPE_SCHEMA_FILE_SHA256 = "728c3ccefc166d2dc64b9aee4df5b4bd243b7a341641652745a3e84c21d7bced"
MANIFEST_SCHEMA_FILE = ROOT / "reports/specs/apf2k8_uniform_selector_patch_manifest.schema.json"
MANIFEST_SCHEMA_FILE_SIZE = 10_646
MANIFEST_SCHEMA_FILE_SHA256 = "f6a596531454e0cd32a40f1550640f5779ea9f6ae4e2a69247c90b121284af3b"

VERIFY_SCHEMA = "apf2k8_uniform_selector_verify/v1"
RECIPE_SCHEMA = "apf2k8_uniform_selector_assignment_recipe/v1"
MANIFEST_SCHEMA = "apf2k8_uniform_selector_patch/v1"
OPERATION = "replace_uniform_selector_byte0_in_both_banks"
MAX_RECIPE_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
BUILT_IN_COUNT = 24
FAMILY_COUNT = 11

BUILT_IN_NAMES = (
    "Americans", "Assassins", "Beasts", "Cobras", "Cougars", "Cyclones",
    "Federals", "Firebirds", "Gunslingers", "Indians", "Iron Men", "Knights",
    "Legends", "Minutemen", "Red Dogs", "Rhinos", "Rollers", "Rustlers",
    "Sailors", "Scorpions", "Sharks", "Top Guns", "Wasps", "Werewolves",
)


class VerifyError(ValueError):
    """The independently reconstructed output violates the frozen contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class FamilyLayout:
    offsets: tuple[tuple[int, int], ...]
    record_indices: tuple[tuple[int, int], ...]
    assets: tuple[int, ...]


@dataclass(frozen=True)
class SelectorLayout:
    families: dict[str, FamilyLayout]
    all_pointer_targets: tuple[int, ...]


def load_compact_authority(
    bound: base.BoundFile,
    size: int,
    digest: str,
    schema: str,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    require(bound.size == size and bound.digest() == digest, f"{label} identity differs")
    raw = bound.read_all(size)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerifyError(f"{label} is invalid JSON") from exc
    canonical = (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    require(isinstance(value, dict) and raw == canonical and value.get("schema") == schema,
            f"{label} canonical/schema identity differs")
    return value, raw


def expected_recipe(allocation: dict[str, Any]) -> dict[str, Any]:
    rows = allocation.get("families")
    require(isinstance(rows, list) and len(rows) == FAMILY_COUNT,
            "allocation family cardinality differs")
    families: list[dict[str, Any]] = []
    for family in rows:
        require(isinstance(family, dict), "allocation family is not an object")
        plan = family.get("built_in_plan")
        assignments = plan.get("assignments") if isinstance(plan, dict) else None
        require(isinstance(assignments, list) and len(assignments) == BUILT_IN_COUNT,
                "allocation assignment cardinality differs")
        normalized: list[dict[str, int]] = []
        for team, row in enumerate(assignments):
            require(isinstance(row, dict) and row.get("team_index") == team,
                    "allocation assignment order differs")
            expected = row.get("expected_retail_asset_index")
            replacement = row.get("replacement_asset_index")
            require(
                not isinstance(expected, bool) and isinstance(expected, int)
                and not isinstance(replacement, bool) and isinstance(replacement, int),
                "allocation assignment contains a non-integer",
            )
            normalized.append({
                "expected_retail_asset_index": expected,
                "replacement_asset_index": replacement,
                "team_index": team,
            })
        families.append({
            "assignments": normalized,
            "catalog_count": family.get("catalog_count"),
            "family": family.get("family"),
            "physical_families": family.get("physical_families"),
            "selector_slot": family.get("selector_slot"),
        })
    return {
        "allocation_strategy": "minimum_changes_maximum_scope_internal_distinctness",
        "claim_flags": {
            "all_family_plans_reach_catalog_upper_bound_requested": True,
            "archive_growth_requested": False,
            "emulator_runtime_visibility_proved": False,
            "online_or_user_slot_authoring_requested": False,
            "original_xbox_360_hardware_proved": False,
            "selector_bytes_1_through_7_authoring_requested": False,
        },
        "families": families,
        "game": {"platform": "Xbox 360", "title": "All-Pro Football 2K8"},
        "operation": OPERATION,
        "schema": RECIPE_SCHEMA,
        "scope": {
            "slot_kind": "built_in",
            "team_count": BUILT_IN_COUNT,
            "team_indices": list(range(BUILT_IN_COUNT)),
        },
        "source_contract": {
            "allocation_report_sha256": ALLOCATION_REPORT_SHA256,
            "decoded_roster_sha256": base.DECODED_SHA256,
            "outer_entry_index": base.OUTER_INDEX,
            "outer_entry_sha256": base.OUTER_SHA256,
            "retail_0A_sha256": base.SOURCE_VOLUME_SHA256,
        },
    }


def validate_recipe(recipe: dict[str, Any], allocation: dict[str, Any]) -> None:
    require(recipe == expected_recipe(allocation),
            "recipe differs from the frozen deterministic built-in all-family plan")


def _family_contracts(allocation: dict[str, Any]) -> list[dict[str, Any]]:
    rows = allocation["families"]
    result: list[dict[str, Any]] = []
    names: set[str] = set()
    slots: set[int] = set()
    for ordinal, row in enumerate(rows):
        require(isinstance(row, dict), f"family contract {ordinal} is not an object")
        name = row.get("family")
        slot = row.get("selector_slot")
        catalog = row.get("catalog_count")
        require(
            isinstance(name, str) and name not in names
            and not isinstance(slot, bool) and isinstance(slot, int) and slot not in slots
            and 0 <= slot < base.SLOTS_PER_BANK
            and not isinstance(catalog, bool) and isinstance(catalog, int) and 1 <= catalog <= 256,
            f"family contract {ordinal} is invalid",
        )
        names.add(name)
        slots.add(slot)
        result.append(row)
    require(len(result) == FAMILY_COUNT, "family contract count differs")
    return result


def derive_selector_layout(
    decoded: bytes,
    allocation: dict[str, Any],
    *,
    require_retail_vectors: bool,
) -> SelectorLayout:
    tables = base.parse_root(decoded)
    team_table = tables[base.TEAM_TABLE]
    config_table = tables[base.CONFIG_TABLE]
    selector_table = tables[base.SELECTOR_TABLE]
    require(
        (team_table.count, team_table.stride) == (40, base.TEAM_STRIDE)
        and (config_table.count, config_table.stride) == (40, base.CONFIG_STRIDE)
        and (selector_table.count, selector_table.stride) == (3724, base.SELECTOR_STRIDE),
        "team/config/selector root-table contract differs",
    )
    targets: list[int] = []
    by_team_slot: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for team in range(40):
        team_record = team_table.offset + team * base.TEAM_STRIDE
        config = base.resolve_relative(
            decoded, team_record + base.TEAM_CONFIG_POINTER_OFFSET, f"team {team} config"
        )
        require(base._aligned_record(config, config_table, base.CONFIG_STRIDE,
                                     f"team {team} config") == team,
                f"team {team} config is not one-to-one")
        for bank in range(base.BANK_COUNT):
            for slot in range(base.SLOTS_PER_BANK):
                field = config + (bank * base.SLOTS_PER_BANK + slot) * 4
                target = base.resolve_relative(
                    decoded, field, f"team {team} bank {bank} slot {slot}"
                )
                index = base._aligned_record(
                    target, selector_table, base.SELECTOR_STRIDE,
                    f"team {team} bank {bank} slot {slot}",
                )
                targets.append(target)
                by_team_slot.setdefault((team, slot), []).append((target, index))
    require(len(targets) == 1120 and len(set(targets)) == 1120,
            "complete selector pointer graph is not one-to-one")

    family_layouts: dict[str, FamilyLayout] = {}
    for contract in _family_contracts(allocation):
        name = contract["family"]
        slot = contract["selector_slot"]
        catalog = contract["catalog_count"]
        offsets: list[tuple[int, int]] = []
        indices: list[tuple[int, int]] = []
        assets: list[int] = []
        for team in range(40):
            records = by_team_slot.get((team, slot), [])
            require(len(records) == 2, f"team {team} family {name} bank count differs")
            pair_offsets = (records[0][0], records[1][0])
            pair_indices = (records[0][1], records[1][1])
            values = (decoded[pair_offsets[0]], decoded[pair_offsets[1]])
            require(values[0] == values[1] and values[0] < catalog,
                    f"team {team} family {name} bank values differ or exceed catalog")
            offsets.append(pair_offsets)
            indices.append(pair_indices)
            assets.append(values[0])
        if require_retail_vectors:
            evidence = contract.get("retail", {}).get("selector_evidence")
            expected = [row.get("retail_asset_index") for row in evidence] if isinstance(evidence, list) else []
            require(assets == expected, f"retail family vector differs: {name}")
        family_layouts[name] = FamilyLayout(tuple(offsets), tuple(indices), tuple(assets))
    return SelectorLayout(family_layouts, tuple(targets))


def build_expected(
    source_entry: bytes,
    source_iff: base.ParsedIFF,
    source_decoded: bytes,
    source_tokens: tuple[base.H7AToken, ...],
    source_consumed: int,
    source_layout: SelectorLayout,
    recipe: dict[str, Any],
    recipe_raw: bytes,
    allocation: dict[str, Any],
    capacity: dict[str, Any],
    output_name: str,
    output_volume_sha256: str,
) -> tuple[bytes, bytes, dict[str, Any], list[int]]:
    wanted = bytearray(source_decoded)
    authorized: list[int] = []
    expected_differences: list[int] = []
    changed_assignment_total = 0
    family_manifest: list[dict[str, Any]] = []
    for family in recipe["families"]:
        name = family["family"]
        source_family = source_layout.families[name]
        replacements = list(source_family.assets)
        changed_teams: list[int] = []
        for assignment in family["assignments"]:
            team = assignment["team_index"]
            expected = assignment["expected_retail_asset_index"]
            replacement = assignment["replacement_asset_index"]
            offsets = source_family.offsets[team]
            require(tuple(source_decoded[offset] for offset in offsets) == (expected, expected),
                    f"team {team} family {name} differs from recipe expectation")
            for offset in offsets:
                authorized.append(offset)
                wanted[offset] = replacement
                if expected != replacement:
                    expected_differences.append(offset)
            replacements[team] = replacement
            if expected != replacement:
                changed_teams.append(team)
        changed_assignment_total += len(changed_teams)
        contract = next(row for row in allocation["families"] if row["family"] == name)
        plan = contract["built_in_plan"]
        distinct_after = len(set(replacements[:BUILT_IN_COUNT]))
        require(distinct_after == plan["catalog_capacity_upper_bound"],
                f"family {name} does not reach its catalog upper bound")
        family_manifest.append({
            "assignment_count": BUILT_IN_COUNT,
            "catalog_capacity_upper_bound": plan["catalog_capacity_upper_bound"],
            "catalog_count": family["catalog_count"],
            "changed_team_count": len(changed_teams),
            "changed_team_indices": changed_teams,
            "distinct_asset_count_after": distinct_after,
            "distinct_asset_count_before": plan["distinct_asset_count_before"],
            "family": name,
            "physical_families": family["physical_families"],
            "selector_slot": family["selector_slot"],
        })
    wanted_bytes = bytes(wanted)
    differences = [
        offset for offset, pair in enumerate(zip(source_decoded, wanted_bytes))
        if pair[0] != pair[1]
    ]
    require(differences == sorted(expected_differences),
            "decoded edit set differs from the exact planned selector bytes")
    require(len(set(authorized)) == 528 and set(differences).issubset(authorized),
            "all-family byte-zero authorization set differs")

    payload, metrics = base.encode_preserving_h7a(
        source_tokens, len(source_iff.payload) - source_consumed, wanted_bytes
    )
    require(len(payload) <= base.MAX_H7A_PAYLOAD_SIZE,
            "reconstructed H7A payload exceeds fixed allocation")
    measurement = capacity["combined"]["built_in_24"]
    changed_offset_digest = sha256_bytes(
        b"".join(offset.to_bytes(4, "big") for offset in differences)
    )
    require(
        len(differences) == measurement["changed_decoded_byte_count"]
        and changed_offset_digest == measurement["changed_decoded_offsets_sha256"]
        and sha256_bytes(wanted_bytes) == measurement["decoded_output_sha256"]
        and len(payload) == measurement["h7a_payload_size_bytes"]
        and sha256_bytes(payload) == measurement["h7a_payload_sha256"],
        "independent deterministic rebuild differs from pinned capacity witness",
    )
    stored = struct.pack(
        ">5I", base.H7A_MAGIC, base.DECODED_SIZE, base.H7A_HEADER_SIZE + len(payload),
        base.H7A_UNKNOWN, base.H7A_SHIFT,
    ) + payload
    header = bytearray(source_entry[: base.IFF_HEADER_SIZE])
    struct.pack_into(
        ">8I", header, base.IFF_BLOCK_TABLE_OFFSET,
        base.IFF_BLOCK_HASH, base.IFF_BLOCK_HASH, 0x20, base.DECODED_SIZE,
        base.H7A_UNKNOWN, base.IFF_HEADER_SIZE, len(stored), 0,
    )
    file_length = base.IFF_HEADER_SIZE + len(stored)
    struct.pack_into(">I", header, 0x08, file_length)
    active = bytes(header) + stored + source_iff.footer
    require(len(active) <= base.OUTER_SIZE, "reconstructed ROST exceeds fixed allocation")
    rebuilt = active + bytes(base.OUTER_SIZE - len(active))
    output_decoded, _tokens, _consumed = base.decode_h7a(payload)
    require(output_decoded == wanted_bytes, "independent output payload decode differs")

    token_metrics = {
        "retail_token_count": len(source_tokens),
        "output_token_count": metrics["output_token_count"],
        "retail_tokens_preserved_semantically": metrics["retail_tokens_preserved_semantically"],
        "retail_tokens_split_or_replaced": metrics["retail_tokens_split_or_replaced"],
        "retail_payload_consumed_bytes": source_consumed,
        "retail_zero_alignment_bytes": len(source_iff.payload) - source_consumed,
    }
    manifest: dict[str, Any] = {
        "claim_flags": {
            "all_family_plans_reach_catalog_upper_bound_offline": True,
            "all_online_and_user_slots_bit_exact": True,
            "archive_growth_required": False,
            "emulator_runtime_visibility_proved": False,
            "original_xbox_360_hardware_proved": False,
            "production_gui_exposed": False,
            "selector_byte_0_filename_ownership_proved": True,
            "selector_bytes_1_through_7_semantics_proved": False,
        },
        "compression": {
            "fixed_payload_limit_bytes": base.MAX_H7A_PAYLOAD_SIZE,
            "headroom_bytes_after": base.MAX_H7A_PAYLOAD_SIZE - len(payload),
            "payload_sha256_after": sha256_bytes(payload),
            "payload_size_after": len(payload),
            "payload_size_before": base.SOURCE_H7A_PAYLOAD_SIZE,
            "shift": base.H7A_SHIFT,
            **token_metrics,
        },
        "families": family_manifest,
        "mode": "changed",
        "preservation": {
            "authorized_decoded_byte_count": len(set(authorized)),
            "changed_decoded_offsets_sha256": changed_offset_digest,
            "decoded_changed_byte_count": len(differences),
            "decoded_output_sha256": sha256_bytes(wanted_bytes),
            "footer_bit_exact": True,
            "online_and_user_team_selector_records_bit_exact": True,
            "opaque_selector_bytes_1_through_7_bit_exact": True,
            "other_decoded_bytes_bit_exact": True,
            "output_zero_tail_bytes": base.OUTER_SIZE - file_length - base.FOOTER_TOTAL,
            "rebuilt_iff_reparsed": True,
        },
        "recipe": {
            "assignment_count": FAMILY_COUNT * BUILT_IN_COUNT,
            "changed_team_family_assignment_count": changed_assignment_total,
            "family_count": FAMILY_COUNT,
            "schema": RECIPE_SCHEMA,
            "sha256": sha256_bytes(recipe_raw),
            "size_bytes": len(recipe_raw),
        },
        "result": {
            "copied_volume": {
                "name": output_name,
                "outside_outer_entry_prefix_sha256": base.SOURCE_PREFIX_SHA256,
                "outside_outer_entry_suffix_sha256": base.SOURCE_SUFFIX_SHA256,
                "sha256": output_volume_sha256,
                "size_bytes": base.SOURCE_VOLUME_SIZE,
            },
            "file_length_after": file_length,
            "outer_entry_sha256": sha256_bytes(rebuilt),
            "outer_entry_size": len(rebuilt),
        },
        "schema": MANIFEST_SCHEMA,
        "source": {
            "allocation_report_sha256": ALLOCATION_REPORT_SHA256,
            "allocation_report_size_bytes": ALLOCATION_REPORT_SIZE,
            "capacity_report_sha256": CAPACITY_REPORT_SHA256,
            "capacity_report_size_bytes": CAPACITY_REPORT_SIZE,
            "decoded_roster_sha256": base.DECODED_SHA256,
            "manifest_schema_sha256": MANIFEST_SCHEMA_FILE_SHA256,
            "manifest_schema_size_bytes": MANIFEST_SCHEMA_FILE_SIZE,
            "outer_entry_index": base.OUTER_INDEX,
            "outer_entry_pack_offset": base.OUTER_OFFSET,
            "outer_entry_sha256": base.OUTER_SHA256,
            "recipe_schema_sha256": RECIPE_SCHEMA_FILE_SHA256,
            "recipe_schema_size_bytes": RECIPE_SCHEMA_FILE_SIZE,
            "retail_0A_sha256": base.SOURCE_VOLUME_SHA256,
            "retail_0A_size_bytes": base.SOURCE_VOLUME_SIZE,
        },
    }
    return rebuilt, wanted_bytes, manifest, differences


def verify(
    source_path: Path,
    recipe_path: Path,
    output_path: Path,
    manifest_path: Path,
    report_path: Path | None = None,
) -> dict[str, Any]:
    with ExitStack() as stack:
        allocation_file = stack.enter_context(base.BoundFile(ALLOCATION_REPORT, "allocation report"))
        capacity_file = stack.enter_context(base.BoundFile(CAPACITY_REPORT, "capacity report"))
        schema_file = stack.enter_context(base.BoundFile(RECIPE_SCHEMA_FILE, "recipe schema"))
        manifest_schema_file = stack.enter_context(
            base.BoundFile(MANIFEST_SCHEMA_FILE, "manifest schema")
        )
        source = stack.enter_context(base.BoundFile(source_path, "retail source 0A"))
        recipe_file = stack.enter_context(base.BoundFile(recipe_path, "all-family recipe"))
        output = stack.enter_context(base.BoundFile(output_path, "copied output 0A"))
        manifest_file = stack.enter_context(base.BoundFile(manifest_path, "writer manifest"))
        bound = [
            allocation_file,
            capacity_file,
            schema_file,
            manifest_schema_file,
            source,
            recipe_file,
            output,
            manifest_file,
        ]
        require(len({item.identity for item in bound}) == len(bound),
                "an authority/input/output pair aliases one inode")
        require(schema_file.size == RECIPE_SCHEMA_FILE_SIZE
                and schema_file.digest() == RECIPE_SCHEMA_FILE_SHA256,
                "recipe schema identity differs")
        require(manifest_schema_file.size == MANIFEST_SCHEMA_FILE_SIZE
                and manifest_schema_file.digest() == MANIFEST_SCHEMA_FILE_SHA256,
                "manifest schema identity differs")
        allocation, _allocation_raw = load_compact_authority(
            allocation_file, ALLOCATION_REPORT_SIZE, ALLOCATION_REPORT_SHA256,
            "apf2k8_uniform_selector_allocation/v1", "allocation report",
        )
        capacity, _capacity_raw = load_compact_authority(
            capacity_file, CAPACITY_REPORT_SIZE, CAPACITY_REPORT_SHA256,
            "apf2k8_uniform_selector_capacity_probe/v1", "capacity report",
        )
        require(capacity.get("source", {}).get("allocation_report_sha256") == ALLOCATION_REPORT_SHA256,
                "capacity report does not bind allocation report")
        require(source.size == base.SOURCE_VOLUME_SIZE and source.supplied_path.name == "0A",
                "source is not the pinned retail 0A shape")
        recipe, recipe_raw = base.load_canonical_json(
            recipe_file, MAX_RECIPE_BYTES, "all-family recipe"
        )
        validate_recipe(recipe, allocation)
        supplied_manifest, _manifest_raw = base.load_canonical_json(
            manifest_file, MAX_MANIFEST_BYTES, "writer manifest"
        )

        source_outer = base.parse_outer_directory(source)
        output_outer = base.parse_outer_directory(output)
        require(source_outer == output_outer, "copied output outer directory routing differs")
        source_entry = source.read(source_outer.pack_offset, source_outer.size)
        output_entry = output.read(output_outer.pack_offset, output_outer.size)
        require(sha256_bytes(source_entry) == base.OUTER_SHA256,
                "retail ROST outer-entry SHA-256 differs")
        source_iff = base.parse_iff(source_entry)
        require(source_iff.file_length == base.SOURCE_FILE_LENGTH
                and len(source_iff.payload) == base.SOURCE_H7A_PAYLOAD_SIZE
                and sha256_bytes(source_iff.footer) == base.FOOTER_SHA256,
                "retail ROST IFF/footer identity differs")
        source_decoded, source_tokens, source_consumed = base.decode_h7a(source_iff.payload)
        require(sha256_bytes(source_decoded) == base.DECODED_SHA256,
                "retail decoded ROST SHA-256 differs")
        source_layout = derive_selector_layout(
            source_decoded, allocation, require_retail_vectors=True
        )
        volume_facts = base.compare_complete_volumes(source, output)
        expected_entry, wanted_decoded, expected_manifest, differences = build_expected(
            source_entry,
            source_iff,
            source_decoded,
            source_tokens,
            source_consumed,
            source_layout,
            recipe,
            recipe_raw,
            allocation,
            capacity,
            output.supplied_path.name,
            str(volume_facts["output_sha256"]),
        )
        require(output_entry == expected_entry,
                "output ROST outer entry differs from independent reconstruction")
        output_iff = base.parse_iff(output_entry)
        output_decoded, _tokens, _consumed = base.decode_h7a(output_iff.payload)
        require(output_decoded == wanted_decoded, "output decoded ROST differs")
        output_layout = derive_selector_layout(
            output_decoded, allocation, require_retail_vectors=False
        )
        for family in recipe["families"]:
            name = family["family"]
            require(output_layout.families[name].offsets == source_layout.families[name].offsets
                    and output_layout.families[name].record_indices == source_layout.families[name].record_indices,
                    f"output family pointer graph differs: {name}")
            expected_assets = list(source_layout.families[name].assets)
            for assignment in family["assignments"]:
                expected_assets[assignment["team_index"]] = assignment["replacement_asset_index"]
            require(output_layout.families[name].assets == tuple(expected_assets),
                    f"output family vector differs: {name}")
        require(supplied_manifest == expected_manifest,
                "writer manifest differs from complete independent reconstruction")
        require(volume_facts["changed_bytes_inside_outer_entry"] == sum(
            left != right for left, right in zip(source_entry, expected_entry)
        ), "full-volume outer-entry difference count differs")

        report = {
            "claims": {
                "all_bytes_outside_outer_entry_bit_exact": True,
                "all_online_and_user_slots_bit_exact": True,
                "complete_manifest_reconstructed": True,
                "emulator_runtime_visibility_proved": False,
                "original_xbox_360_hardware_proved": False,
                "selector_byte_0_only": True,
                "selector_bytes_1_through_7_bit_exact": True,
            },
            "decoded_changed_byte_count": len(differences),
            "decoded_output_sha256": sha256_bytes(wanted_decoded),
            "family_count": FAMILY_COUNT,
            "manifest_sha256": manifest_file.digest(),
            "outer_entry_sha256": sha256_bytes(output_entry),
            "output_volume_sha256": volume_facts["output_sha256"],
            "payload_size_after": len(output_iff.payload),
            "recipe_sha256": sha256_bytes(recipe_raw),
            "schema": VERIFY_SCHEMA,
        }
        for item in bound:
            item.assert_stable()
        if report_path is not None:
            reservation = base.ReportReservation(report_path, bound)
            try:
                reservation.commit(base.canonical_json_bytes(report))
                for item in bound:
                    item.assert_stable()
                reservation.finalize()
            finally:
                reservation.close()
        return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-index", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output-volume", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--json", type=Path, help="new canonical verification report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = verify(
            args.source_index, args.recipe, args.output_volume, args.manifest, args.json
        )
        print(
            "APF_UNIFORM_SELECTOR_VERIFY_PASS "
            f"families={report['family_count']} "
            f"changed_bytes={report['decoded_changed_byte_count']} "
            f"payload={report['payload_size_after']} "
            "runtime=false hardware=false"
        )
        return 0
    except (VerifyError, base.VerifyError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
