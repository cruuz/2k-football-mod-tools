#!/usr/bin/env python3
"""Audit uniform texture content aliases without inventing storage aliases.

The NFL tables expose decoded texture identity for every uniform selector.
The compatible-writer reports independently expose each selected resource's
fixed XISO span.  Joining the two proves whether equal-looking textures occupy
the same bytes or merely have equal content.

APF is the inverse case: team selector records name a small jersey catalog.
The report keeps bank numbers neutral and records the exact teams that select
each physical jersey asset.  A separate fail-closed CLI now writes the bounded
ROST selector edit and has independent offline verification; runtime behavior
and public-GUI exposure remain unproved.
"""

from __future__ import annotations

import argparse
import copy
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "uniform_texture_sharing_audit/v2"
LEGACY_SCHEMA = "uniform_texture_sharing_audit/v1"

DEFAULT_PATHS = {
    "nfl_uniform_inventory": ROOT / "reports/assets/nfl2k5_uniform_inventory.json",
    "nfl_tset_textures": ROOT / "reports/assets/nfl2k5_uniform_tset_textures.tsv",
    "nfl_standalone_textures":
        ROOT / "reports/assets/nfl2k5_uniform_standalone_txtr.tsv",
    "nfl_jersey_compatibility":
        ROOT / "reports/assets/nfl2k5_jersey_tset_compatibility.json",
    "nfl_sleeve_compatibility":
        ROOT / "reports/assets/nfl2k5_sleeve_tset_compatibility.json",
    "nfl_pants_compatibility":
        ROOT / "reports/assets/nfl2k5_pants_tset_compatibility.json",
    "nfl_helmet_compatibility":
        ROOT / "reports/assets/nfl2k5_live_helmet_txtr_compatibility.json",
    "apf_uniform_inventory": ROOT / "reports/assets/apf_uniform_inventory.json",
    "apf_team_assets": ROOT / "reports/assets/apf_uniform_team_assets.tsv",
    "apf_jersey_layout": ROOT / "reports/assets/apf_jersey_family_layout.json",
}

EXPECTED_SHA256 = {
    "nfl_uniform_inventory":
        "b9799b6f67b023f51b56695443fe2d5ff9e5ee3abc08a2c567f4c3c6cd5d04b8",
    "nfl_tset_textures":
        "f8c60d618cab8326d7a215936a2e66a75d9f399c13c0087608fbc2010bcd3abd",
    "nfl_standalone_textures":
        "2775f97c840af6ddc7af6a5b705ed902518a6e912aca79603e78d47fd6f603b8",
    "nfl_jersey_compatibility":
        "046d03546242c11478d39b48d7f6f80b5f2009c85641b5c81abdaa6f8171cacd",
    "nfl_sleeve_compatibility":
        "72a25d908135322a6c15c1f19f2f575224ab224c8b8c4c6969f5b4ba2359ae2b",
    "nfl_pants_compatibility":
        "cab15d4f03c69f5143edd40f567ec038d2425bba80bf9dd1a85b642e144ac1ac",
    "nfl_helmet_compatibility":
        "1b7bdbb67a28b9d70531c3af80ff67574a7d60ef421bcf42ba9422f0f278e6ff",
    "apf_uniform_inventory":
        "b3ad0e44af0163b30857e20c7c4e90ceb89cbc3dbc8cc41508fce3aaf1c136c7",
    "apf_team_assets":
        "d112710582b223d32425a79eedf321a2d9f61a01152c1c9d03b74f250231d82b",
    "apf_jersey_layout":
        "b60783b9c47b57e9b9f545e95f5c17d3c850e263e0d7d453aa6c3be4a0f809e4",
}

TSET_FAMILIES = {
    "torso": {
        "compatibility": "nfl_jersey_compatibility",
        "chunk_index": 1,
        "names": ("jersey00", "jersey00_mud"),
        "writer": "tools/nfl2k5_uniform_jersey_png_workflow.py",
        "runtime": (
            "Detroit current AWAY jersey00 is visible on live coin-toss "
            "players; other selectors and gameplay are not generalized"
        ),
    },
    "pants": {
        "compatibility": "nfl_pants_compatibility",
        "chunk_index": 2,
        "names": ("pants00", "pants00_mud"),
        "writer": "tools/nfl2k5_uniform_pants_png_workflow.py",
        "runtime": "offline fixed-span writer proved; runtime visibility untested",
    },
    "sleeve": {
        "compatibility": "nfl_sleeve_compatibility",
        "chunk_index": 3,
        "names": ("sleeve00", "sleeve00_mud"),
        "writer": "tools/nfl2k5_uniform_sleeve_png_workflow.py",
        "runtime": "offline fixed-span writer proved; runtime visibility untested",
    },
}


class AuditError(ValueError):
    """Raised when a pinned source or ownership invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_sources(paths: dict[str, Path]) -> tuple[dict[str, bytes], dict[str, Any]]:
    payloads: dict[str, bytes] = {}
    evidence: dict[str, Any] = {}
    for key in sorted(DEFAULT_PATHS):
        path = paths[key]
        payload = path.read_bytes()
        actual = digest(payload)
        require(actual == EXPECTED_SHA256[key], f"pinned source changed: {key}")
        payloads[key] = payload
        evidence[key] = {
            "path": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
            "size": len(payload),
            "sha256": actual,
        }
    return payloads, evidence


def tsv_rows(payload: bytes) -> list[dict[str, str]]:
    text = payload.decode("utf-8")
    return list(csv.DictReader(text.splitlines(), delimiter="\t"))


def selector_key(value: dict[str, Any]) -> str:
    selector = value["selector"]
    return f"{selector['asset_code']}{selector['side']}{selector['variant']}"


def interval_audit(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    intervals = sorted(
        (
            int(row["xiso_absolute_span_offset"]),
            int(row["xiso_absolute_span_offset"]) + int(row["span_size"]),
            str(row["selector"]),
            str(row["family"]),
        )
        for row in rows
    )
    overlaps: list[dict[str, Any]] = []
    widest = intervals[0]
    for right in intervals[1:]:
        if right[0] < widest[1]:
            overlaps.append({
                "left": {"start": widest[0], "end": widest[1],
                         "selector": widest[2], "family": widest[3]},
                "right": {"start": right[0], "end": right[1],
                          "selector": right[2], "family": right[3]},
            })
        if right[1] > widest[1]:
            widest = right
    require(not overlaps, "NFL writable resource spans overlap")
    return {
        "write_unit_count": len(intervals),
        "distinct_interval_count": len(set((x[0], x[1]) for x in intervals)),
        "cross_selector_overlap_count": len(overlaps),
        "all_intervals_pairwise_disjoint": True,
    }


def group_id(prefix: str, identity: tuple[str, ...]) -> str:
    encoded = "\0".join((prefix, *identity)).encode("ascii")
    return f"{prefix}-{digest(encoded)[:16]}"


def owner_projection(row: dict[str, str], span: dict[str, Any]) -> dict[str, Any]:
    logical = row["logical_name"]
    return {
        "selector": logical[:-4] if logical.endswith(".IFF") else logical,
        "logical_name": logical,
        "asset_code": row["asset_code"],
        "side": row["side_code"],
        "variant": int(row["variant_id"]),
        "team": row["roster_current_names"],
        "abbreviation": row["roster_current_abbreviations"],
        "style": row["style_display"],
        "outer_index": int(row["outer_index"]),
        "xiso_absolute_span_offset": int(span["xiso_absolute_span_offset"]),
        "span_size": int(span["span_size"]),
    }


def role_groups(rows: list[dict[str, str]], name: str,
                span_by_selector: dict[str, dict[str, Any]], family: str) \
        -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selected = [row for row in rows if row["name"] == name]
    require(len(selected) == 634, f"{name} selector corpus changed")
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in selected:
        key = row["logical_name"].removesuffix(".IFF")
        require(key in span_by_selector, f"missing {family} span for {key}")
        groups[(
            str(span_by_selector[key]["decoded_sha256"]),
            row["base_pixel_sha256"],
            row["palette_bgra_sha256"],
        )].append(row)
    selector_shared = [members for members in groups.values() if len(members) > 1]
    cross_asset = [
        members for members in selector_shared
        if len({row["asset_code"] for row in members}) > 1
    ]
    records: list[dict[str, Any]] = []
    for members in cross_asset:
        first_key = members[0]["logical_name"].removesuffix(".IFF")
        identity = (
            str(span_by_selector[first_key]["decoded_sha256"]),
            members[0]["base_pixel_sha256"],
            members[0]["palette_bgra_sha256"],
        )
        owners = []
        for row in sorted(members, key=lambda item: item["logical_name"]):
            key = row["logical_name"].removesuffix(".IFF")
            require(key in span_by_selector, f"missing {family} span for {key}")
            owners.append(owner_projection(row, span_by_selector[key]))
        records.append({
            "group_id": group_id(f"nfl-{name}", identity),
            "family": family,
            "texture_name": name,
            "identity_basis": (
                "exact complete decoded TSET SHA-256; role-specific base-pixel "
                "and full BGRA-palette hashes also match"
            ),
            "decoded_tset_sha256": identity[0],
            "base_pixel_sha256": identity[1],
            "palette_bgra_sha256": identity[2],
            "owner_count": len(owners),
            "asset_code_count": len({owner["asset_code"] for owner in owners}),
            "owners": owners,
        })
    records.sort(key=lambda item: item["group_id"])
    return ({
        "texture_name": name,
        "selector_count": len(selected),
        "exact_visual_identity_count": len(groups),
        "selector_shared_identity_group_count": len(selector_shared),
        "cross_asset_code_identity_group_count": len(cross_asset),
        "cross_asset_code_affected_selector_count": sum(len(x) for x in cross_asset),
        "maximum_cross_asset_code_group_size": max(map(len, cross_asset), default=0),
    }, records)


def helmet_groups(standalone_rows: list[dict[str, str]], resources: list[dict[str, Any]],
                  family: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selected = [row for row in standalone_rows if row["name"] == family]
    require(len(selected) == 634, f"{family} selector corpus changed")
    span_by_selector = {
        selector_key(row): row for row in resources if row["family"] == family
    }
    require(len(span_by_selector) == 634, f"{family} span corpus changed")
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in selected:
        key = row["logical_name"].removesuffix(".IFF")
        require(key in span_by_selector, f"missing {family} span for {key}")
        groups[(str(span_by_selector[key]["decoded_sha256"]), row["rgba_sha256"])].append(row)
    selector_shared = [members for members in groups.values() if len(members) > 1]
    cross_asset = [
        members for members in selector_shared
        if len({row["asset_code"] for row in members}) > 1
    ]
    records: list[dict[str, Any]] = []
    for members in cross_asset:
        first_key = members[0]["logical_name"].removesuffix(".IFF")
        decoded_sha = str(span_by_selector[first_key]["decoded_sha256"])
        rgba_sha = members[0]["rgba_sha256"]
        owners = []
        for row in sorted(members, key=lambda item: item["logical_name"]):
            key = row["logical_name"].removesuffix(".IFF")
            owners.append(owner_projection(row, span_by_selector[key]))
        records.append({
            "group_id": group_id(f"nfl-{family}", (decoded_sha, rgba_sha)),
            "family": "live_helmet",
            "texture_name": family,
            "identity_basis": (
                "exact complete decoded TXTR SHA-256; decoded base RGBA also matches"
            ),
            "decoded_txtr_sha256": decoded_sha,
            "rgba_sha256": rgba_sha,
            "owner_count": len(owners),
            "asset_code_count": len({owner["asset_code"] for owner in owners}),
            "owners": owners,
        })
    records.sort(key=lambda item: item["group_id"])
    return ({
        "texture_name": family,
        "selector_count": len(selected),
        "exact_visual_identity_count": len(groups),
        "selector_shared_identity_group_count": len(selector_shared),
        "cross_asset_code_identity_group_count": len(cross_asset),
        "cross_asset_code_affected_selector_count": sum(len(x) for x in cross_asset),
        "maximum_cross_asset_code_group_size": max(map(len, cross_asset), default=0),
    }, records)


def build_nfl(payloads: dict[str, bytes]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    inventory = json.loads(payloads["nfl_uniform_inventory"])
    require(inventory["schema"] == "nfl2k5_uniform_inventory/v1",
            "NFL uniform inventory schema changed")
    require(inventory["summary"]["uniform_package_count"] == 634,
            "NFL uniform package count changed")
    selector_catalog = [{
        "selector": row["logical_name"].removesuffix(".IFF"),
        "logical_name": row["logical_name"],
        "asset_code": row["asset_code"],
        "side": row["side_code"],
        "variant": int(row["variant_id"]),
        "team": row["roster_current_names"],
        "abbreviation": row["roster_current_abbreviations"],
        "style": row["style_display"],
        "outer_index": int(row["outer_index"]),
    } for row in inventory["packages"]]
    selector_catalog.sort(key=lambda item: item["selector"])
    require(len(selector_catalog) == 634 and
            len({item["selector"] for item in selector_catalog}) == 634,
            "NFL uniform selector catalog changed")
    tset_rows = tsv_rows(payloads["nfl_tset_textures"])
    standalone_rows = tsv_rows(payloads["nfl_standalone_textures"])

    physical_rows: list[dict[str, Any]] = []
    families: list[dict[str, Any]] = []
    all_groups: list[dict[str, Any]] = []
    for family, spec in TSET_FAMILIES.items():
        compatibility = json.loads(payloads[spec["compatibility"]])
        packages = compatibility["packages"]
        require(len(packages) == 634, f"NFL {family} compatibility count changed")
        span_by_selector = {selector_key(row): row for row in packages}
        require(len(span_by_selector) == 634, f"NFL {family} selectors are ambiguous")
        for key, span in span_by_selector.items():
            require(span["source_xiso_span_matches"], f"NFL {family} XISO mismatch: {key}")
            physical_rows.append({
                "selector": key,
                "family": family,
                "xiso_absolute_span_offset": span["xiso_absolute_span_offset"],
                "span_size": span["span_size"],
            })
        summaries = []
        for name in spec["names"]:
            summary, groups = role_groups(tset_rows, name, span_by_selector, family)
            summaries.append(summary)
            all_groups.extend(groups)
        families.append({
            "family": family,
            "chunk_index": spec["chunk_index"],
            "selector_count": 634,
            "texture_names": list(spec["names"]),
            "decoded_intra_resource_alias": (
                "clean and _mud descriptors share one pixel/mip index chain "
                "inside each selector TSET and retain separate palettes"
            ),
            "fixed_span_writer": spec["writer"],
            "runtime_boundary": spec["runtime"],
            "roles": summaries,
        })

    helmet = json.loads(payloads["nfl_helmet_compatibility"])
    resources = helmet["resources"]
    require(len(resources) == 1268, "NFL live helmet resource count changed")
    for row in resources:
        require(row["source_xiso_span_matches"], "NFL helmet XISO span mismatch")
        physical_rows.append({
            "selector": selector_key(row),
            "family": row["family"],
            "xiso_absolute_span_offset": row["xiso_absolute_span_offset"],
            "span_size": row["span_size"],
        })
    helmet_summaries = []
    for family in ("helmet00", "helmet02"):
        summary, groups = helmet_groups(standalone_rows, resources, family)
        helmet_summaries.append(summary)
        all_groups.extend(groups)
    families.append({
        "family": "live_helmet",
        "selector_count": 634,
        "resource_count": 1268,
        "texture_names": ["helmet00", "helmet02"],
        "fixed_span_writer": "tools/nfl_live_helmet_txtr_xiso_workflow.py",
        "runtime_boundary": "offline fixed-span writer proved; runtime visibility untested",
        "roles": helmet_summaries,
    })

    all_groups.sort(key=lambda item: item["group_id"])
    physical = interval_audit(physical_rows)
    require(physical["write_unit_count"] == 3170,
            "NFL writable physical resource count changed")
    return ({
        "game": "ESPN NFL 2K5 (USA Xbox)",
        "uniform_selector_count": 634,
        "selectors": selector_catalog,
        "identity_warning": (
            "Equal decoded hashes are content aliases relevant to emulator "
            "texture replacement; they are not evidence of shared on-disc bytes."
        ),
        "physical_storage": {
            **physical,
            "result": (
                "Every audited torso, pants, sleeve, helmet00, and helmet02 "
                "selector resource occupies its own fixed, non-overlapping XISO span."
            ),
        },
        "families": families,
        "cross_asset_code_content_alias_group_count": len(all_groups),
        "cross_asset_code_content_alias_owner_count": sum(
            item["owner_count"] for item in all_groups
        ),
        "cross_asset_code_content_alias_groups": all_groups,
        "practical_fix": {
            "status": "available for the audited fixed-span writer families",
            "method": (
                "Import artwork into the selected selector's existing resource span; "
                "do not duplicate an outer entry or patch a pointer."
            ),
            "archive_growth_required": False,
            "xdvdfs_relayout_required": False,
            "code_or_pointer_change_required": False,
            "arbitrary_input_guaranteed_to_fit": False,
            "fit_gate": (
                "The rebuilt compressed stream must fit that selector's exact retail "
                "allocation; writers refuse overflow without producing an output."
            ),
            "hash_swap_caveat": (
                "A replacement system keyed only by decoded texture hash will still "
                "replace every equal-content owner until one owner is changed on disc."
            ),
        },
    }, all_groups)


def build_apf(payloads: dict[str, bytes]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    inventory = json.loads(payloads["apf_uniform_inventory"])
    layout = json.loads(payloads["apf_jersey_layout"])
    require(inventory["schema"] == "apf_uniform_inventory/v1",
            "APF uniform inventory schema changed")
    require(layout["schema"] == "apf_jersey_family_layout/v1",
            "APF jersey layout schema changed")
    family = next(item for item in inventory["family_specs"]
                  if item["family"] == "jersey")
    require(family["catalog_count"] == 24 and len(layout["jerseys"]) == 24,
            "APF jersey catalog count changed")
    rows = [row for row in tsv_rows(payloads["apf_team_assets"])
            if row["families"] == "jersey"]
    require(len(rows) == 80, "APF jersey selector row count changed")
    by_asset: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        require(row["selector_slot"] == "4", "APF jersey selector slot changed")
        by_asset[int(row["asset_index_byte_0"])].append(row)

    asset_records = []
    tsv_records: list[dict[str, Any]] = []
    for asset in range(24):
        owners = sorted(by_asset.get(asset, []),
                        key=lambda item: (int(item["team_index"]), int(item["bank"])))
        projected = [{
            "team_index": int(row["team_index"]),
            "team": row["team_name"],
            "abbreviation": row["abbreviation"],
            "slot_kind": row["slot_kind"],
            "bank": int(row["bank"]),
            "selector_record_index": int(row["selector_record_index"]),
            "selector_record_offset": row["selector_record_offset"],
            "raw_record_hex": row["raw_record_hex"],
        } for row in owners]
        asset_records.append({
            "asset_index": asset,
            "outer_name": f"uniform_jersey_{asset:02d}.iff",
            "selector_owner_count": len(projected),
            "team_count": len({row["team_index"] for row in projected}),
            "built_in_team_count": len({
                row["team_index"] for row in projected
                if row["slot_kind"] == "built_in_team"
            }),
            "shared_by_multiple_teams": len({
                row["team_index"] for row in projected
            }) > 1,
            "owners": projected,
        })
        for row in projected:
            tsv_records.append({
                "asset_index": asset,
                "outer_name": f"uniform_jersey_{asset:02d}.iff",
                "asset_team_count": asset_records[-1]["team_count"],
                "asset_built_in_team_count": asset_records[-1]["built_in_team_count"],
                **row,
            })

    built_in = sorted(
        (row for row in rows if row["slot_kind"] == "built_in_team" and row["bank"] == "0"),
        key=lambda item: int(item["team_index"]),
    )
    require(len(built_in) == 24, "APF built-in team count changed")
    current_assets = [int(row["asset_index_byte_0"]) for row in built_in]
    unused = list(family["unreferenced_catalog_asset_indices"])
    require(unused == [1, 3, 5, 7, 9, 10, 14, 15, 16, 17, 18, 20, 21, 22],
            "APF unreferenced jersey asset set changed")

    # Preserve the first built-in owner of each currently used asset.  Give the
    # remaining built-ins the lowest still-unassigned catalog slot.  Asset 12
    # must be used to make all 24 built-ins mutually unique, but it remains
    # selected by every retail online/user placeholder; the plan says so.
    assigned: set[int] = set()
    available = [asset for asset in range(24) if asset not in set(current_assets)]
    plan = []
    for row in built_in:
        current = int(row["asset_index_byte_0"])
        if current not in assigned:
            target = current
            reason = "retains first built-in owner of this retail asset"
        else:
            require(available, "APF unique built-in allocation exhausted")
            target = available.pop(0)
            reason = "uses a catalog slot not assigned to another built-in team"
        assigned.add(target)
        plan.append({
            "team_index": int(row["team_index"]),
            "team": row["team_name"],
            "abbreviation": row["abbreviation"],
            "retail_asset_index": current,
            "proposed_unique_asset_index": target,
            "changes_selector_byte_0": current != target,
            "reason": reason,
            "retail_placeholder_conflict": target == 12,
        })
    require(len(assigned) == 24 and not available,
            "APF built-in allocation is not a 24-slot permutation")
    require(sum(item["retail_placeholder_conflict"] for item in plan) == 1,
            "APF placeholder conflict boundary changed")

    return ({
        "game": "All-Pro Football 2K8 (USA Xbox 360)",
        "jersey_catalog_asset_count": 24,
        "selector_row_count": len(rows),
        "team_count": 40,
        "built_in_team_count": 24,
        "online_placeholder_count": 8,
        "user_placeholder_count": 8,
        "used_asset_indices": sorted(by_asset),
        "unreferenced_asset_indices": unused,
        "assets": asset_records,
        "physical_storage": {
            "distinct_jersey_outer_entry_count": len(layout["jerseys"]),
            "all_24_layouts_and_fixed_allocations_structurally_proved":
                layout["family_equivalence"][
                    "all_controlled_solid_rebuilds_fit_fixed_allocations"
                ],
            "selector_alias_kind": (
                "Multiple ROST selector records store the same asset-index byte and "
                "therefore resolve the same physical uniform_jersey_NN.iff entry."
            ),
        },
        "built_in_unique_allocation_plan": {
            "status": (
                "allocation plan admitted by the independently verified offline "
                "selector writer; matched runtime witness remains unproved"
            ),
            "all_24_built_in_teams_mutually_unique": True,
            "uses_all_24_catalog_assets": True,
            "archive_growth_required": False,
            "jersey_outer_entry_relayout_required": False,
            "roster_selector_change_required": True,
            "selector_bytes_to_change_per_remapped_team": (
                "byte 0 in both bank-0 and bank-1 slot-4 selector records; bytes 1..7 "
                "must remain exact"
            ),
            "retail_placeholder_boundary": (
                "Only 24 jersey assets exist for 40 on-disc team slots. Making all "
                "24 built-ins mutually unique assigns asset 12 to one built-in while "
                "the 16 online/user placeholders still select asset 12. Full 40-slot "
                "isolation is impossible without adding catalog capacity or changing "
                "the executable/filename ownership model."
            ),
            "plan": plan,
        },
        "practical_fix": {
            "status": (
                "safe fail-closed offline CLI writer proved; hidden from the public "
                "GUI pending matched runtime witness"
            ),
            "safe_offline_cli_dealias_writer_available": True,
            "public_gui_dealias_writer_available": False,
            "runtime_witness_available": False,
            "writer": "tools/apf_jersey_selector_patch.py",
            "independent_verifier": "tools/apf_jersey_selector_verify.py",
            "machine_readable_spec": (
                "reports/specs/apf2k8_roster_jersey_selector_writeback.v1.json"
            ),
            "already_proved": (
                "all 24 jersey package layouts, asset-index filename selection, exact "
                "selector record derivation, nine-mip fixed-allocation jersey writer, "
                "bounded H7A/IFF ROST reconstruction, byte-exact identity, exact "
                "two-byte targeted remap, exact 30-byte 24-built-in allocation, and "
                "independent whole-volume verification"
            ),
            "missing": (
                "matched retail-versus-edited Xenia runtime proof, original-hardware "
                "proof, and production GUI integration"
            ),
            "arbitrary_input_guaranteed_to_fit": False,
        },
    }, tsv_records)


def build_report(paths: dict[str, Path] | None = None) \
        -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    selected_paths = dict(DEFAULT_PATHS if paths is None else paths)
    payloads, sources = load_sources(selected_paths)
    nfl, nfl_groups = build_nfl(payloads)
    apf, apf_rows = build_apf(payloads)
    report = {
        "schema": SCHEMA,
        "scope": {
            "mode": "read_only_inventory_join",
            "retail_game_files_written": False,
            "emulator_started": False,
            "claim": (
                "Exact cross-team content aliases and physical ownership for audited "
                "NFL uniform writer families, plus APF jersey selector ownership."
            ),
        },
        "sources": sources,
        "nfl2k5": nfl,
        "apf2k8": apf,
    }
    return report, nfl_groups, apf_rows


def legacy_v1_report(report: dict[str, Any]) -> dict[str, Any]:
    """Project the immutable pre-selector-writer v1 evidence document."""

    require(report.get("schema") == SCHEMA, "current sharing report schema changed")
    legacy = copy.deepcopy(report)
    legacy["schema"] = LEGACY_SCHEMA
    legacy["apf2k8"]["built_in_unique_allocation_plan"]["status"] = (
        "static allocation plan only; no selector writer emitted"
    )
    legacy["apf2k8"]["practical_fix"] = {
        "status": "not yet exposed as a safe de-alias writer",
        "already_proved": (
            "all 24 jersey package layouts, asset-index filename selection, exact "
            "selector record addresses, nine-mip fixed-allocation jersey writer"
        ),
        "missing": (
            "bounded on-disc ROST H7A/IFF rebuild for the two selector bytes per "
            "team, independent verification, and matched Xenia runtime proof"
        ),
        "arbitrary_input_guaranteed_to_fit": False,
    }
    return legacy


def write_nfl_tsv(path: Path, groups: list[dict[str, Any]]) -> None:
    fields = [
        "group_id", "family", "texture_name", "identity_basis",
        "decoded_tset_sha256", "decoded_txtr_sha256", "base_pixel_sha256",
        "palette_bgra_sha256", "rgba_sha256",
        "owner_count", "asset_code_count", "selector", "logical_name",
        "asset_code", "side", "variant", "team", "abbreviation", "style",
        "outer_index", "xiso_absolute_span_offset", "span_size",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        for group in groups:
            for owner in group["owners"]:
                writer.writerow({
                    **{field: group.get(field, "") for field in fields},
                    **owner,
                })


def write_apf_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "asset_index", "outer_name", "asset_team_count",
        "asset_built_in_team_count", "team_index", "team", "abbreviation",
        "slot_kind", "bank", "selector_record_index", "selector_record_offset",
        "raw_record_hex",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path,
                        default=ROOT / "reports/assets/uniform_texture_sharing.v2.json")
    parser.add_argument(
        "--legacy-v1-report",
        type=Path,
        help="optionally reproduce the immutable pre-selector-writer v1 report",
    )
    parser.add_argument("--nfl-tsv", type=Path,
                        default=ROOT / "reports/assets/nfl2k5_uniform_texture_sharing.tsv")
    parser.add_argument("--apf-tsv", type=Path,
                        default=ROOT / "reports/assets/apf2k8_jersey_selector_sharing.tsv")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report, nfl_groups, apf_rows = build_report()
    args.report.write_bytes(canonical_json(report))
    if args.legacy_v1_report is not None:
        args.legacy_v1_report.write_bytes(canonical_json(legacy_v1_report(report)))
    write_nfl_tsv(args.nfl_tsv, nfl_groups)
    write_apf_tsv(args.apf_tsv, apf_rows)
    print(
        "UNIFORM_TEXTURE_SHARING_AUDIT_OK "
        f"nfl_physical={report['nfl2k5']['physical_storage']['write_unit_count']} "
        f"nfl_cross_team_groups={len(nfl_groups)} "
        f"apf_assets={report['apf2k8']['jersey_catalog_asset_count']} "
        f"apf_selectors={len(apf_rows)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
