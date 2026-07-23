#!/usr/bin/env python3
"""Measure APF uniform selector plans against the pinned ROST H7A ceiling.

This companion to ``apf_uniform_selector_allocation.py`` is read-only.  It
applies each deterministic plan to an in-memory decoded copy of the exact
retail ROST, invokes the already checked token-preserving H7A encoder, and
records whether the result fits the fixed roster allocation.  A fit is binary
feasibility evidence, not recipe authority and not a selector writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import apf_jersey_selector_patch as roster_writer
import apf_uniform_selector_allocation as allocation


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
SCHEMA = "apf2k8_uniform_selector_capacity_probe/v1"


class ProbeError(ValueError):
    """The allocation-to-ROST feasibility probe failed closed."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _plan_wanted(
    decoded: bytes,
    family: dict[str, Any],
    scope_key: str,
) -> tuple[bytes, list[int]]:
    plan = family[scope_key]
    evidence = family["retail"]["selector_evidence"]
    assignments = plan["assignments"]
    if len(assignments) != plan["scope_team_count"]:
        raise ProbeError("allocation assignment cardinality drift")

    wanted = bytearray(decoded)
    authorized: list[int] = []
    expected_differences: list[int] = []
    for assignment in assignments:
        team_index = assignment["team_index"]
        if team_index >= len(evidence) or evidence[team_index]["team_index"] != team_index:
            raise ProbeError("allocation selector evidence team order drift")
        expected = assignment["expected_retail_asset_index"]
        replacement = assignment["replacement_asset_index"]
        if evidence[team_index]["retail_asset_index"] != expected:
            raise ProbeError("allocation expected retail asset disagrees with evidence")
        records = evidence[team_index]["bank_selector_records"]
        if [record["bank"] for record in records] != [0, 1]:
            raise ProbeError("allocation bank record order drift")
        offsets = [int(record["selector_record_offset"], 16) for record in records]
        if len(set(offsets)) != 2 or any(
            offset < 0 or offset + roster_writer.SELECTOR_STRIDE > len(decoded)
            for offset in offsets
        ):
            raise ProbeError("allocation selector offset is invalid")
        if [decoded[offset] for offset in offsets] != [expected, expected]:
            raise ProbeError("decoded ROST selector byte differs from allocation evidence")
        for offset in offsets:
            wanted[offset] = replacement
            authorized.append(offset)
            if replacement != expected:
                expected_differences.append(offset)

    if len(authorized) != len(set(authorized)):
        raise ProbeError("allocation plan aliases a selector record")
    actual_differences = [
        index
        for index, (before, after) in enumerate(zip(decoded, wanted))
        if before != after
    ]
    if actual_differences != sorted(expected_differences):
        raise ProbeError("in-memory edit set differs from the planned selector byte set")
    if len(actual_differences) != plan["changed_selector_byte_count_both_banks"]:
        raise ProbeError("planned changed selector byte count drift")
    return bytes(wanted), actual_differences


def _encode_measurement(
    original_payload: bytes,
    decoded: bytes,
    wanted: bytes,
    changed_offsets: list[int],
) -> dict[str, Any]:
    if changed_offsets:
        payload, metrics = roster_writer.encode_preserving_h7a(
            original_payload,
            decoded,
            wanted,
            roster_writer.H7A_SHIFT,
        )
    else:
        payload = original_payload
        tokens, consumed = roster_writer.parse_h7a_tokens(
            original_payload,
            roster_writer.DECODED_SIZE,
            roster_writer.H7A_SHIFT,
        )
        metrics = {
            "output_token_count": len(tokens),
            "retail_payload_consumed_bytes": consumed,
            "retail_token_count": len(tokens),
            "retail_tokens_preserved_semantically": len(tokens),
            "retail_tokens_split_or_replaced": 0,
            "retail_zero_alignment_bytes": len(original_payload) - consumed,
        }
    if roster_writer.apf_inner.decompress_h7a(
        payload,
        len(wanted),
        roster_writer.H7A_SHIFT,
    ) != wanted:
        raise ProbeError("measured H7A payload does not decode to the planned ROST")
    return {
        "changed_decoded_byte_count": len(changed_offsets),
        "changed_decoded_offsets_sha256": sha256_bytes(
            b"".join(offset.to_bytes(4, "big") for offset in changed_offsets)
        ),
        "decoded_output_sha256": sha256_bytes(wanted),
        "fixed_h7a_payload_limit_bytes": roster_writer.MAX_H7A_PAYLOAD_SIZE,
        "fits_fixed_h7a_payload_limit": len(payload) <= roster_writer.MAX_H7A_PAYLOAD_SIZE,
        "h7a_payload_headroom_bytes": roster_writer.MAX_H7A_PAYLOAD_SIZE - len(payload),
        "h7a_payload_sha256": sha256_bytes(payload),
        "h7a_payload_size_bytes": len(payload),
        "token_metrics": metrics,
    }


def _combined_wanted(
    decoded: bytes,
    families: list[dict[str, Any]],
    scope_key: str,
) -> tuple[bytes, list[int]]:
    wanted = bytearray(decoded)
    changed: list[int] = []
    for family in families:
        family_wanted, family_changed = _plan_wanted(decoded, family, scope_key)
        for offset in family_changed:
            if offset in changed or wanted[offset] != decoded[offset]:
                raise ProbeError("family plans collide on a decoded selector byte")
            wanted[offset] = family_wanted[offset]
            changed.append(offset)
    changed.sort()
    actual = [
        index
        for index, (before, after) in enumerate(zip(decoded, wanted))
        if before != after
    ]
    if actual != changed:
        raise ProbeError("combined in-memory edit set drift")
    return bytes(wanted), changed


def build_probe(index_path: Path, inventory_path: Path) -> dict[str, Any]:
    inventory, inventory_raw = allocation.load_inventory(inventory_path)
    allocation_report = allocation.build_report(inventory, inventory_raw)
    allocation_raw = allocation.canonical_json_bytes(allocation_report)
    (
        _,
        _,
        _,
        original_entry,
        original_stored,
        decoded,
        _,
    ) = roster_writer._validate_source(index_path)
    original_payload = original_stored[20:]
    if len(original_payload) != roster_writer.SOURCE_H7A_PAYLOAD_SIZE:
        raise ProbeError("retail H7A payload size drift")

    family_rows: list[dict[str, Any]] = []
    for family in allocation_report["families"]:
        scopes: dict[str, Any] = {}
        for report_key, scope_name in (
            ("built_in_plan", "built_in_24"),
            ("all_team_plan", "all_40"),
        ):
            wanted, changed = _plan_wanted(decoded, family, report_key)
            scopes[scope_name] = _encode_measurement(
                original_payload,
                decoded,
                wanted,
                changed,
            )
        family_rows.append({
            "catalog_count": family["catalog_count"],
            "family": family["family"],
            "physical_families": family["physical_families"],
            "scopes": scopes,
            "selector_slot": family["selector_slot"],
        })

    combined: dict[str, Any] = {}
    for report_key, scope_name in (
        ("built_in_plan", "built_in_24"),
        ("all_team_plan", "all_40"),
    ):
        wanted, changed = _combined_wanted(
            decoded,
            allocation_report["families"],
            report_key,
        )
        measurement = _encode_measurement(
            original_payload,
            decoded,
            wanted,
            changed,
        )
        expected = allocation_report["combined_plans"][scope_name][
            "changed_selector_byte_count_both_banks"
        ]
        if measurement["changed_decoded_byte_count"] != expected:
            raise ProbeError("combined allocation changed-byte count drift")
        combined[scope_name] = measurement

    if not all(
        scope["fits_fixed_h7a_payload_limit"]
        for family in family_rows
        for scope in family["scopes"].values()
    ) or not all(scope["fits_fixed_h7a_payload_limit"] for scope in combined.values()):
        raise ProbeError("one or more deterministic selector plans exceed the fixed ROST ceiling")

    return {
        "claim_boundary": {
            "archive_volume_created_or_modified": False,
            "binary_fit_is_recipe_or_write_authority": False,
            "combined_all_40_plan_is_safe_for_online_or_user_slots": False,
            "independent_generic_verifier_exists": False,
            "in_memory_decoded_selector_bytes_only": True,
            "non_jersey_selector_writer_exists": False,
            "runtime_visibility_proved": False,
        },
        "combined": combined,
        "families": family_rows,
        "schema": SCHEMA,
        "source": {
            "allocation_report_sha256": sha256_bytes(allocation_raw),
            "allocation_report_size_bytes": len(allocation_raw),
            "decoded_roster_sha256": sha256_bytes(decoded),
            "inventory_sha256": sha256_bytes(inventory_raw),
            "retail_h7a_payload_sha256": sha256_bytes(original_payload),
            "retail_h7a_payload_size_bytes": len(original_payload),
            "retail_outer_entry_sha256": sha256_bytes(original_entry),
            "retail_outer_entry_size_bytes": len(original_entry),
            "retail_volume_sha256": roster_writer.SOURCE_VOLUME_SHA256,
            "retail_volume_size_bytes": roster_writer.SOURCE_VOLUME_SIZE,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=allocation.DEFAULT_INVENTORY,
        help="exact byte copy of the pinned APF uniform inventory",
    )
    parser.add_argument("--json", type=Path, help="write canonical report to a new path")
    args = parser.parse_args(argv)
    try:
        report = build_probe(args.index, args.inventory)
        payload = allocation.canonical_json_bytes(report)
        if args.json is not None:
            with args.json.open("xb") as descriptor:
                descriptor.write(payload)
        print(payload.decode("utf-8"), end="")
    except (
        ProbeError,
        allocation.AllocationError,
        roster_writer.PatchError,
        roster_writer.apf_inner.FormatError,
        roster_writer.apf_outer.FormatError,
        roster_writer.apf_roster.RosterError,
        OSError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
