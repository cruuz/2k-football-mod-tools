#!/usr/bin/env python3
"""Fail-closed APF 2K8 deterministic built-in all-family selector writer.

The only admitted recipe is the frozen minimum-change plan for all eleven
filename-owned selector slots across built-in teams 0..23. Targets are
re-derived through the retail ROST pointer graph; report offsets are never
write authority. The writer changes byte 0 in both neutral banks, preserves
bytes 1..7 and every other decoded byte, performs a bounded token-preserving
H7A/IFF rebuild, and patches only a newly copied retail ``0A`` volume.

This is offline write authority. Runtime visibility, online/user-slot writes,
and Xbox 360 hardware acceptance remain explicitly unproved.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import stat
import struct
import sys
from typing import Any

# The installed Windows runtime uses an embeddable CPython ``._pth`` file,
# which does not automatically add this script's directory to ``sys.path``.
# Restore it before importing sibling tools so direct subprocess launches work
# the same way as a normal Python installation.
_here = str(Path(__file__).resolve().parent)
if _here not in sys.path:
    sys.path.insert(0, _here)

import apf_jersey_selector_patch as transport


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

RECIPE_SCHEMA = "apf2k8_uniform_selector_assignment_recipe/v1"
MANIFEST_SCHEMA = "apf2k8_uniform_selector_patch/v1"
OPERATION = "replace_uniform_selector_byte0_in_both_banks"
MAX_RECIPE_BYTES = 256 * 1024
BUILT_IN_COUNT = 24
EXPECTED_FAMILY_COUNT = 11

BUILT_IN_NAMES = transport.BUILT_IN_NAMES


class PatchError(ValueError):
    """The all-family recipe or output violates the frozen write boundary."""


@dataclass(frozen=True)
class FamilyLayout:
    offsets: tuple[tuple[int, int], ...]
    record_indices: tuple[tuple[int, int], ...]
    assets: tuple[int, ...]


@dataclass(frozen=True)
class SelectorLayout:
    families: dict[str, FamilyLayout]
    all_pointer_targets: tuple[int, ...]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_compact_authority(
    path: Path, size: int, digest: str, schema: str, label: str
) -> tuple[dict[str, Any], bytes]:
    raw = transport._read_bound_file(path, size, f"checked {label}")
    if len(raw) != size or sha256_bytes(raw) != digest:
        raise PatchError(f"checked {label} identity drift")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatchError(f"checked {label} is invalid JSON") from exc
    expected = (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    if not isinstance(value, dict) or raw != expected or value.get("schema") != schema:
        raise PatchError(f"checked {label} canonical/schema drift")
    return value, raw


def load_authorities() -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    for path, size, digest, label in (
        (RECIPE_SCHEMA_FILE, RECIPE_SCHEMA_FILE_SIZE, RECIPE_SCHEMA_FILE_SHA256, "recipe schema"),
        (MANIFEST_SCHEMA_FILE, MANIFEST_SCHEMA_FILE_SIZE, MANIFEST_SCHEMA_FILE_SHA256, "manifest schema"),
    ):
        schema_raw = transport._read_bound_file(path, size, f"checked all-family {label}")
        if len(schema_raw) != size or sha256_bytes(schema_raw) != digest:
            raise PatchError(f"checked all-family {label} identity drift")
    allocation, allocation_raw = _load_compact_authority(
        ALLOCATION_REPORT,
        ALLOCATION_REPORT_SIZE,
        ALLOCATION_REPORT_SHA256,
        "apf2k8_uniform_selector_allocation/v1",
        "all-family allocation report",
    )
    capacity, capacity_raw = _load_compact_authority(
        CAPACITY_REPORT,
        CAPACITY_REPORT_SIZE,
        CAPACITY_REPORT_SHA256,
        "apf2k8_uniform_selector_capacity_probe/v1",
        "all-family capacity report",
    )
    if capacity.get("source", {}).get("allocation_report_sha256") != ALLOCATION_REPORT_SHA256:
        raise PatchError("capacity report does not bind the allocation report")
    return allocation, allocation_raw, capacity, capacity_raw


def expected_recipe(allocation: dict[str, Any]) -> dict[str, Any]:
    families: list[dict[str, Any]] = []
    rows = allocation.get("families")
    if not isinstance(rows, list) or len(rows) != EXPECTED_FAMILY_COUNT:
        raise PatchError("allocation report family cardinality drift")
    for family in rows:
        plan = family.get("built_in_plan")
        assignments = plan.get("assignments") if isinstance(plan, dict) else None
        if not isinstance(assignments, list) or len(assignments) != BUILT_IN_COUNT:
            raise PatchError("allocation report built-in assignment cardinality drift")
        normalized: list[dict[str, int]] = []
        for team, row in enumerate(assignments):
            if not isinstance(row, dict) or row.get("team_index") != team:
                raise PatchError("allocation report built-in assignment order drift")
            normalized.append({
                "expected_retail_asset_index": row["expected_retail_asset_index"],
                "replacement_asset_index": row["replacement_asset_index"],
                "team_index": team,
            })
        families.append({
            "assignments": normalized,
            "catalog_count": family["catalog_count"],
            "family": family["family"],
            "physical_families": family["physical_families"],
            "selector_slot": family["selector_slot"],
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
            "decoded_roster_sha256": transport.DECODED_SHA256,
            "outer_entry_index": transport.OUTER_INDEX,
            "outer_entry_sha256": transport.OUTER_SHA256,
            "retail_0A_sha256": transport.SOURCE_VOLUME_SHA256,
        },
    }


def load_recipe(path: Path) -> tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]:
    allocation, _allocation_raw, capacity, _capacity_raw = load_authorities()
    recipe, raw = transport._load_canonical_json(path, MAX_RECIPE_BYTES, "all-family recipe")
    wanted = expected_recipe(allocation)
    if recipe != wanted:
        raise PatchError("recipe differs from the frozen deterministic built-in all-family plan")
    return recipe, raw, allocation, capacity


def _family_contracts(allocation: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_slots: set[int] = set()
    for ordinal, family in enumerate(allocation["families"]):
        name = family.get("family")
        slot = family.get("selector_slot")
        catalog = family.get("catalog_count")
        if (
            not isinstance(name, str)
            or name in seen_names
            or isinstance(slot, bool)
            or not isinstance(slot, int)
            or slot in seen_slots
            or not 0 <= slot < transport.SLOTS_PER_BANK
            or isinstance(catalog, bool)
            or not isinstance(catalog, int)
            or not 1 <= catalog <= 256
        ):
            raise PatchError(f"allocation family contract {ordinal} is invalid")
        seen_names.add(name)
        seen_slots.add(slot)
        result.append(family)
    if len(result) != EXPECTED_FAMILY_COUNT:
        raise PatchError("allocation family contract count drift")
    return result


def derive_selector_layout(
    decoded: bytes,
    allocation: dict[str, Any],
    *,
    require_retail_vectors: bool,
) -> SelectorLayout:
    tables_list, _ = transport.apf_roster.parse_root(decoded)
    tables = tuple(tables_list)
    team_table = tables[transport.TEAM_TABLE]
    config_table = tables[transport.CONFIG_TABLE]
    selector_table = tables[transport.SELECTOR_TABLE]
    if (
        (team_table.count, team_table.stride) != (40, transport.TEAM_STRIDE)
        or (config_table.count, config_table.stride) != (40, transport.CONFIG_STRIDE)
        or (selector_table.count, selector_table.stride) != (3724, transport.SELECTOR_STRIDE)
    ):
        raise PatchError("ROST team/config/selector table contract drift")

    all_targets: list[int] = []
    targets_by_team_slot: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for team in range(40):
        team_record = team_table.offset + team * transport.TEAM_STRIDE
        config = transport._relative_target(
            decoded, team_record + transport.TEAM_CONFIG_POINTER_OFFSET, f"team {team} config"
        )
        if transport._aligned_index(
            config, config_table, transport.CONFIG_STRIDE, f"team {team} config"
        ) != team:
            raise PatchError(f"team {team} config mapping is not one-to-one")
        for bank in range(transport.BANK_COUNT):
            for slot in range(transport.SLOTS_PER_BANK):
                field = config + (bank * transport.SLOTS_PER_BANK + slot) * 4
                target = transport._relative_target(
                    decoded, field, f"team {team} bank {bank} slot {slot}"
                )
                index = transport._aligned_index(
                    target,
                    selector_table,
                    transport.SELECTOR_STRIDE,
                    f"team {team} bank {bank} slot {slot}",
                )
                all_targets.append(target)
                targets_by_team_slot.setdefault((team, slot), []).append((target, index))
    if len(all_targets) != 40 * transport.BANK_COUNT * transport.SLOTS_PER_BANK:
        raise PatchError("selector pointer graph cardinality drift")
    if len(set(all_targets)) != len(all_targets):
        raise PatchError("two team-bank-slot pointers alias one selector record")

    family_layouts: dict[str, FamilyLayout] = {}
    for contract in _family_contracts(allocation):
        name = contract["family"]
        slot = contract["selector_slot"]
        catalog = contract["catalog_count"]
        offsets: list[tuple[int, int]] = []
        indices: list[tuple[int, int]] = []
        assets: list[int] = []
        for team in range(40):
            records = targets_by_team_slot.get((team, slot), [])
            if len(records) != 2:
                raise PatchError(f"team {team} family {name} bank count drift")
            pair_offsets = (records[0][0], records[1][0])
            pair_indices = (records[0][1], records[1][1])
            values = (decoded[pair_offsets[0]], decoded[pair_offsets[1]])
            if values[0] != values[1] or values[0] >= catalog:
                raise PatchError(f"team {team} family {name} bank values differ or exceed catalog")
            offsets.append(pair_offsets)
            indices.append(pair_indices)
            assets.append(values[0])
        if require_retail_vectors:
            evidence = contract.get("retail", {}).get("selector_evidence")
            expected = [row.get("retail_asset_index") for row in evidence] if isinstance(evidence, list) else []
            if assets != expected:
                raise PatchError(f"retail family vector drift: {name}")
        family_layouts[name] = FamilyLayout(tuple(offsets), tuple(indices), tuple(assets))
    return SelectorLayout(family_layouts, tuple(all_targets))


def _difference_offsets(before: bytes, after: bytes) -> list[int]:
    if len(before) != len(after):
        raise PatchError("decoded comparison length drift")
    return [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]


def build_patch(index_path: Path, recipe_path: Path) -> transport.BuildResult:
    recipe, recipe_raw, allocation, capacity = load_recipe(recipe_path)
    (
        _,
        entry,
        record,
        original_entry,
        original_stored,
        decoded,
        _,
    ) = transport._validate_source(index_path)
    layout = derive_selector_layout(decoded, allocation, require_retail_vectors=True)
    wanted = bytearray(decoded)
    authorized_offsets: list[int] = []
    expected_differences: list[int] = []
    family_manifest: list[dict[str, Any]] = []
    changed_assignment_total = 0
    for family in recipe["families"]:
        name = family["family"]
        source_family = layout.families[name]
        changed_teams: list[int] = []
        replacements = list(source_family.assets)
        for assignment in family["assignments"]:
            team = assignment["team_index"]
            expected = assignment["expected_retail_asset_index"]
            replacement = assignment["replacement_asset_index"]
            offsets = source_family.offsets[team]
            if tuple(decoded[offset] for offset in offsets) != (expected, expected):
                raise PatchError(f"team {team} family {name} differs from recipe expectation")
            for offset in offsets:
                authorized_offsets.append(offset)
                wanted[offset] = replacement
                if expected != replacement:
                    expected_differences.append(offset)
            replacements[team] = replacement
            if expected != replacement:
                changed_teams.append(team)
        changed_assignment_total += len(changed_teams)
        plan = next(row for row in allocation["families"] if row["family"] == name)["built_in_plan"]
        distinct_after = len(set(replacements[:BUILT_IN_COUNT]))
        if distinct_after != plan["catalog_capacity_upper_bound"]:
            raise PatchError(f"family {name} did not reach its pinned built-in upper bound")
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
    differences = _difference_offsets(decoded, wanted_bytes)
    if differences != sorted(expected_differences):
        raise PatchError("decoded edit set differs from the exact planned selector bytes")
    if not set(differences).issubset(authorized_offsets) or len(set(authorized_offsets)) != 528:
        raise PatchError("all-family byte-zero authorization set drift")

    payload, metrics = transport.encode_preserving_h7a(
        original_stored[20:], decoded, wanted_bytes, transport.H7A_SHIFT
    )
    if len(payload) > transport.MAX_H7A_PAYLOAD_SIZE:
        raise PatchError("rebuilt H7A payload exceeds the fixed allocation")
    expected_capacity = capacity["combined"]["built_in_24"]
    changed_offset_digest = sha256_bytes(
        b"".join(offset.to_bytes(4, "big") for offset in differences)
    )
    if (
        len(differences) != expected_capacity["changed_decoded_byte_count"]
        or changed_offset_digest != expected_capacity["changed_decoded_offsets_sha256"]
        or sha256_bytes(wanted_bytes) != expected_capacity["decoded_output_sha256"]
        or len(payload) != expected_capacity["h7a_payload_size_bytes"]
        or sha256_bytes(payload) != expected_capacity["h7a_payload_sha256"]
    ):
        raise PatchError("rebuilt deterministic plan differs from the pinned capacity witness")

    stored = struct.pack(
        ">5I",
        transport.apf_inner.H7A_MAGIC,
        transport.DECODED_SIZE,
        20 + len(payload),
        transport.H7A_UNKNOWN,
        transport.H7A_SHIFT,
    ) + payload
    header = bytearray(original_entry[: transport.IFF_HEADER_SIZE])
    block = record.blocks[0]
    struct.pack_into(
        ">8I",
        header,
        transport.apf_inner.IFF_HEADER_SIZE,
        block.name_hash,
        block.type_hash,
        block.unknown_08,
        transport.DECODED_SIZE,
        transport.H7A_UNKNOWN,
        transport.IFF_HEADER_SIZE,
        len(stored),
        block.indexed,
    )
    file_length = transport.IFF_HEADER_SIZE + len(stored)
    struct.pack_into(">I", header, 0x08, file_length)
    footer = original_entry[
        transport.SOURCE_FILE_LENGTH : transport.SOURCE_FILE_LENGTH + transport.FOOTER_TOTAL
    ]
    active = bytes(header) + stored + footer
    if len(active) > transport.OUTER_SIZE:
        raise PatchError("rebuilt ROST exceeds the fixed outer allocation")
    rebuilt = active + bytes(transport.OUTER_SIZE - len(active))
    memory = transport.BytesReader(rebuilt)
    rebuilt_record = transport.apf_inner.parse_iff(memory, entry)
    rebuilt_decoded = transport.apf_inner.decode_block(memory, rebuilt_record, 0, 16 * 1024 * 1024)
    if rebuilt_record.warnings or rebuilt_decoded != wanted_bytes:
        raise PatchError("rebuilt all-family ROST did not reparse/decode exactly")
    if rebuilt[file_length : file_length + transport.FOOTER_TOTAL] != footer:
        raise PatchError("rebuilt all-family ROST footer drift")
    if any(rebuilt[file_length + transport.FOOTER_TOTAL :]):
        raise PatchError("rebuilt all-family ROST tail is not zero")
    output_layout = derive_selector_layout(
        rebuilt_decoded, allocation, require_retail_vectors=False
    )
    for family in recipe["families"]:
        name = family["family"]
        if (
            output_layout.families[name].offsets != layout.families[name].offsets
            or output_layout.families[name].record_indices != layout.families[name].record_indices
        ):
            raise PatchError(f"output family pointer graph drift: {name}")
        expected_assets = list(layout.families[name].assets)
        for assignment in family["assignments"]:
            expected_assets[assignment["team_index"]] = assignment["replacement_asset_index"]
        if output_layout.families[name].assets != tuple(expected_assets):
            raise PatchError(f"output family assignment drift: {name}")

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
            "fixed_payload_limit_bytes": transport.MAX_H7A_PAYLOAD_SIZE,
            "headroom_bytes_after": transport.MAX_H7A_PAYLOAD_SIZE - len(payload),
            "payload_sha256_after": sha256_bytes(payload),
            "payload_size_after": len(payload),
            "payload_size_before": transport.SOURCE_H7A_PAYLOAD_SIZE,
            "shift": transport.H7A_SHIFT,
            **metrics,
        },
        "families": family_manifest,
        "mode": "changed",
        "preservation": {
            "authorized_decoded_byte_count": len(set(authorized_offsets)),
            "changed_decoded_offsets_sha256": changed_offset_digest,
            "decoded_changed_byte_count": len(differences),
            "decoded_output_sha256": sha256_bytes(wanted_bytes),
            "footer_bit_exact": True,
            "online_and_user_team_selector_records_bit_exact": True,
            "opaque_selector_bytes_1_through_7_bit_exact": True,
            "other_decoded_bytes_bit_exact": True,
            "output_zero_tail_bytes": transport.OUTER_SIZE - file_length - transport.FOOTER_TOTAL,
            "rebuilt_iff_reparsed": True,
        },
        "recipe": {
            "assignment_count": EXPECTED_FAMILY_COUNT * BUILT_IN_COUNT,
            "changed_team_family_assignment_count": changed_assignment_total,
            "family_count": EXPECTED_FAMILY_COUNT,
            "schema": RECIPE_SCHEMA,
            "sha256": sha256_bytes(recipe_raw),
            "size_bytes": len(recipe_raw),
        },
        "result": {
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
            "decoded_roster_sha256": transport.DECODED_SHA256,
            "manifest_schema_sha256": MANIFEST_SCHEMA_FILE_SHA256,
            "manifest_schema_size_bytes": MANIFEST_SCHEMA_FILE_SIZE,
            "outer_entry_index": transport.OUTER_INDEX,
            "outer_entry_pack_offset": transport.OUTER_OFFSET,
            "outer_entry_sha256": transport.OUTER_SHA256,
            "recipe_schema_sha256": RECIPE_SCHEMA_FILE_SHA256,
            "recipe_schema_size_bytes": RECIPE_SCHEMA_FILE_SIZE,
            "retail_0A_sha256": transport.SOURCE_VOLUME_SHA256,
            "retail_0A_size_bytes": transport.SOURCE_VOLUME_SIZE,
        },
    }
    return transport.BuildResult(rebuilt, manifest)


def write_output(
    index_path: Path, recipe_path: Path, output_volume: Path, manifest_path: Path
) -> dict[str, Any]:
    index_path = index_path.expanduser()
    recipe_path = recipe_path.expanduser()
    output_volume = transport._new_output_path(output_volume, "output volume")
    manifest_path = transport._new_output_path(manifest_path, "manifest")
    transport.transport._preflight_output_paths(  # type: ignore[attr-defined]
        [
            index_path,
            recipe_path,
            ALLOCATION_REPORT,
            CAPACITY_REPORT,
            RECIPE_SCHEMA_FILE,
            MANIFEST_SCHEMA_FILE,
        ],
        [("output volume", output_volume), ("manifest", manifest_path)],
    )
    source: transport.BoundSourceVolume | None = None
    output_reservation: transport.BoundOutputReservation | None = None
    manifest_reservation: transport.BoundOutputReservation | None = None
    keep = False
    try:
        result = build_patch(index_path, recipe_path)
        source = transport._bind_source_volume(index_path)
        output_reservation = transport._reserve_bound_output(
            output_volume, stat.S_IMODE(source.metadata.st_mode)
        )
        manifest_reservation = transport._reserve_bound_output(manifest_path, 0o644)
        copied, output_times = transport._write_bound_copied_volume(
            source, output_reservation, result.entry
        )
        result.manifest["result"]["copied_volume"] = {
            "name": output_volume.name,
            "outside_outer_entry_prefix_sha256": copied["outside_replacement"]["prefix_sha256"],
            "outside_outer_entry_suffix_sha256": copied["outside_replacement"]["suffix_sha256"],
            "sha256": copied["output_volume_sha256"],
            "size_bytes": copied["volume_size"],
        }
        document = transport.canonical_json_bytes(result.manifest)
        manifest_times = transport._commit_bound_output(manifest_reservation, document)
        transport._assert_bound_source(source)
        transport._assert_bound_output(
            output_reservation,
            expected_size=transport.SOURCE_VOLUME_SIZE,
            expected_times=output_times,
        )
        transport._assert_bound_output(
            manifest_reservation,
            expected_size=len(document),
            expected_times=manifest_times,
        )
        keep = True
        return result.manifest
    finally:
        if manifest_reservation is not None:
            transport._close_bound_output(manifest_reservation, keep=keep)
        if output_reservation is not None:
            transport._close_bound_output(output_reservation, keep=keep)
        if source is not None:
            try:
                import os
                os.close(source.descriptor)
            except OSError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="pinned user-owned retail APF 0A")
    parser.add_argument("--recipe", required=True, type=Path, help="canonical deterministic all-family recipe")
    parser.add_argument("--output-volume", required=True, type=Path, help="new copied 0A to create")
    parser.add_argument("--manifest", required=True, type=Path, help="new canonical manifest to create")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = write_output(args.index, args.recipe, args.output_volume, args.manifest)
        print(
            "APF_UNIFORM_SELECTOR_PATCH_PASS "
            f"families={manifest['recipe']['family_count']} "
            f"assignments={manifest['recipe']['assignment_count']} "
            f"changed_assignments={manifest['recipe']['changed_team_family_assignment_count']} "
            f"changed_bytes={manifest['preservation']['decoded_changed_byte_count']} "
            f"payload={manifest['compression']['payload_size_after']} "
            f"headroom={manifest['compression']['headroom_bytes_after']} "
            "runtime=false hardware=false"
        )
        return 0
    except (
        PatchError,
        transport.PatchError,
        transport.apf_outer.FormatError,
        transport.apf_inner.FormatError,
        transport.apf_roster.RosterError,
        transport.transport.PatchError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
