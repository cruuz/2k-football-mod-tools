#!/usr/bin/env python3
"""Audit all 24 APF shoulder-color packages and paired selector ownership.

The audit is read-only.  It proves one descriptor/mip/IFF class across
``uniform_shoulder_00..23``, enumerates every team/bank use of selector slot
11, pairs the independently stored ``uniform_shoulder_normal_00..23`` files,
and exercises a controlled nine-mip fixed-allocation rebuild in memory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import zlib

import apf_inner
import apf_outer
import apf_shoulder_color_transport as transport
import apf_texture_patch as archive_patch
import apf_uniform_mip_patch as bc3_backend
import apf_xenos_mip_layout as xenos_mips


SCHEMA = "apf_shoulder_family_layout/v1"
EXPECTED_VOLUME_SIZE = 1_140_850_688
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
EXPECTED_INVENTORY_SHA256 = "b3ad0e44af0163b30857e20c7c4e90ceb89cbc3dbc8cc41508fce3aaf1c136c7"
WORKSPACE = Path(__file__).resolve().parents[1]
INVENTORY = WORKSPACE / "reports/assets/apf_uniform_inventory.json"
SOLID_RGBA = (255, 0, 255, 255)


class FamilyLayoutError(ValueError):
    """Raised when retail shoulder evidence differs from the proved class."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def outer_id(name: str) -> int:
    return zlib.crc32(name.upper().encode("ascii")) & 0xFFFFFFFF


def hx(value: int) -> str:
    return f"0x{value:08x}"


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _selector_uses() -> dict[int, list[dict[str, object]]]:
    payload = INVENTORY.read_bytes()
    if sha256(payload) != EXPECTED_INVENTORY_SHA256:
        raise FamilyLayoutError("APF uniform inventory hash changed")
    inventory = json.loads(payload)
    if (
        inventory["source"]["archive_index"]
        != "extracted/All-Pro Football 2K8 (USA)/0A"
        or inventory["source"]["archive_volume_sizes"]["0A"]
        != EXPECTED_VOLUME_SIZE
    ):
        raise FamilyLayoutError("uniform inventory source identity changed")
    result = {index: [] for index in range(24)}
    teams = inventory["team_selector_graph"]["teams"]
    if len(teams) != 40:
        raise FamilyLayoutError("uniform team roster changed")
    for team in teams:
        if [bank["bank"] for bank in team["banks"]] != [0, 1]:
            raise FamilyLayoutError("uniform bank roster changed")
        for bank in team["banks"]:
            selector = bank["selectors"][11]
            if (
                selector["slot"] != 11
                or selector["families"] != ["shoulder", "shoulder_normal"]
                or selector["semantic_status"]
                != "filename selector proved by XEX 0x849D6BD0"
            ):
                raise FamilyLayoutError("shoulder selector ownership changed")
            asset = selector["asset_index_byte_0"]
            if type(asset) is not int or asset not in result:
                raise FamilyLayoutError("shoulder selector index is out of range")
            result[asset].append(
                {
                    "team_index": team["team_index"],
                    "team_name": team["display_name"],
                    "abbreviation": team["abbreviation"],
                    "slot_kind": team["slot_kind"],
                    "bank": bank["bank"],
                    "selector_record_index": selector["selector_record_index"],
                    "selector_record_offset": selector["selector_record_offset"],
                }
            )
    if sum(map(len, result.values())) != 80:
        raise FamilyLayoutError("shoulder selector graph no longer has 80 uses")
    return result


def _part_rows(
    item: apf_inner.IFFFile, blocks: list[bytes]
) -> list[dict[str, object]]:
    return [
        {
            "part_index": index,
            "block_index": part.block_index,
            "offset": part.offset,
            "length": part.length,
            "sha256": sha256(
                blocks[part.block_index][part.offset : part.offset + part.length]
            ),
        }
        for index, part in enumerate(item.parts)
    ]


def _analyze(
    reader: apf_inner.ArchiveReader,
    entry: apf_outer.Entry,
    normal_entry: apf_outer.Entry,
    asset_index: int,
    uses: list[dict[str, object]],
    solid_block: bytes,
    reference_descriptor: dict[str, object] | None,
    reference_layout: list[dict[str, object]] | None,
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    name = f"uniform_shoulder_{asset_index:02d}.iff"
    normal_name = f"uniform_shoulder_normal_{asset_index:02d}.iff"
    for label, target in ((name, entry), (normal_name, normal_entry)):
        if len(target.segments) != 1 or target.segments[0].pack_name != "0A":
            raise FamilyLayoutError(f"{label}: not one physical 0A segment")
    record = apf_inner.parse_iff(reader, entry)
    original_entry = reader.read(entry, 0, entry.size)
    normal_bytes = reader.read(normal_entry, 0, normal_entry.size)
    blocks = [
        apf_inner.decode_block(reader, record, index, 1 << 30)
        for index in range(record.block_count)
    ]
    stored = [
        reader.read(entry, block.start_offset, block.stored_length)
        for block in record.blocks
    ]
    target, descriptor, texture = transport._validate_structure(record, blocks)  # type: ignore[attr-defined]
    shifts = [block.wrapper.shift if block.wrapper else None for block in record.blocks]
    if shifts != [9, 9]:
        raise FamilyLayoutError(f"{name}: H7A shift profile changed")
    if reference_descriptor is not None and canonical(descriptor) != canonical(
        reference_descriptor
    ):
        raise FamilyLayoutError(f"{name}: complete descriptor drift")
    locations = xenos_mips.derive_layout(descriptor)
    layout = [item.manifest() for item in locations]
    if len(locations) != 9:
        raise FamilyLayoutError(f"{name}: expected nine stored levels")
    if reference_layout is not None and canonical(layout) != canonical(reference_layout):
        raise FamilyLayoutError(f"{name}: mip layout drift")
    if [
        (item.level, item.origin_block_x, item.origin_block_y)
        for item in locations[6:]
    ] != [(6, 4, 0), (7, 2, 0), (8, 1, 0)]:
        raise FamilyLayoutError(f"{name}: packed-tail origins drift")
    if xenos_mips.transport_roundtrip(texture, locations) != texture:
        raise FamilyLayoutError(f"{name}: retail BC3 transport not bit-exact")
    linear = [xenos_mips.extract_linear_bc3(texture, item) for item in locations]

    mask = bc3_backend._active_byte_mask(len(texture), locations)  # type: ignore[attr-defined]
    inactive_before = bc3_backend._hash_inactive(texture, mask)  # type: ignore[attr-defined]
    solid_texture = texture
    for location in locations:
        wanted = solid_block * location.logical_block_count
        solid_texture = xenos_mips.insert_linear_bc3(
            solid_texture, location, wanted
        )
        if xenos_mips.extract_linear_bc3(solid_texture, location) != wanted:
            raise FamilyLayoutError(f"{name}: controlled mip insert failed")
    if bc3_backend._hash_inactive(solid_texture, mask) != inactive_before:  # type: ignore[attr-defined]
        raise FamilyLayoutError(f"{name}: inactive bytes changed")
    rebuilt, iff = transport._rebuild_entry(  # type: ignore[attr-defined]
        entry, record, original_entry, blocks, stored, solid_texture
    )
    if len(rebuilt) != entry.size:
        raise FamilyLayoutError(f"{name}: fixed allocation changed")
    if record.footer is None:
        raise FamilyLayoutError(f"{name}: missing footer")
    footer_size = 8 + record.footer.payload_size
    tail = original_entry[record.file_length + footer_size :]
    if any(tail):
        raise FamilyLayoutError(f"{name}: nonzero allocation tail")
    siblings = [record.files[index] for index in (0, 1, 2)]
    return {
        "asset_index": asset_index,
        "outer_name": name,
        "outer_name_id": hx(entry.name_id),
        "outer_table_index": entry.table_index,
        "physical": {
            "pack_name": "0A",
            "pack_offset": entry.segments[0].pack_offset,
            "virtual_offset": entry.virtual_offset,
        },
        "outer_allocation": {
            "size": entry.size,
            "sha256": sha256(original_entry),
            "slack_before": len(tail),
            "slack_tail_all_zero": True,
        },
        "iff": {
            "header_size": record.header_size,
            "file_length_excluding_footer": record.file_length,
            "block_count": record.block_count,
            "file_count": record.file_count,
            "warnings": record.warnings,
            "h7a_shift_profile": shifts,
            "blocks": [
                {
                    "index": block.descriptor_index,
                    "start_offset": block.start_offset,
                    "uncompressed_length": block.uncompressed_length,
                    "stored_length": block.stored_length,
                    "stored_sha256": sha256(raw),
                    "decoded_sha256": sha256(decoded),
                    "is_h7a_compressed": block.is_compressed,
                }
                for block, raw, decoded in zip(record.blocks, stored, blocks)
            ],
            "file_names": [item.name for item in record.files],
        },
        "inner_file": {
            "index": target.index,
            "name": target.name,
            "type_name": target.type_name,
            "parts": _part_rows(target, blocks),
            "texture_sha256": sha256(texture),
        },
        "preserved_sibling_files": [
            {"index": item.index, "name": item.name, "parts": _part_rows(item, blocks)}
            for item in siblings
        ],
        "paired_normal_package": {
            "outer_name": normal_name,
            "outer_name_id": hx(normal_entry.name_id),
            "outer_table_index": normal_entry.table_index,
            "allocation_size": normal_entry.size,
            "allocation_sha256": sha256(normal_bytes),
            "same_selector_slot_and_asset_index": True,
            "physically_separate_from_color_package": True,
        },
        "txtr_descriptor": descriptor,
        "nine_level_layout": [
            {**item.manifest(), "linear_bc3_sha256": sha256(level)}
            for item, level in zip(locations, linear)
        ],
        "team_bank_use_count": len(uses),
        "team_bank_uses": uses,
        "controlled_solid_rebuild_in_memory": {
            "rgba": list(SOLID_RGBA),
            "inactive_padding_bit_exact": True,
            "transport_bit_exact": xenos_mips.transport_roundtrip(
                solid_texture, locations
            ) == solid_texture,
            "rebuilt_entry_length": len(rebuilt),
            "rebuilt_entry_sha256": sha256(rebuilt),
            "fixed_outer_allocation": True,
            "iff": iff,
            "entry_or_volume_written": False,
        },
    }, descriptor, layout


def analyze(index_path: Path) -> dict[str, object]:
    index_path = index_path.expanduser().resolve(strict=True)
    before = index_path.stat()
    if (
        before.st_size != EXPECTED_VOLUME_SIZE
        or sha256_file(index_path) != EXPECTED_VOLUME_SHA256
    ):
        raise FamilyLayoutError("source is not pinned retail APF 2K8 0A")
    uses = _selector_uses()
    archive = apf_outer.parse_archive(index_path)
    by_id = {entry.name_id: entry for entry in archive.entries}
    if len(by_id) != len(archive.entries):
        raise FamilyLayoutError("duplicate outer name IDs")
    solid_block = archive_patch.encode_bc3_block([SOLID_RGBA] * 16)
    if any(
        tuple(pixel) != SOLID_RGBA
        for pixel in apf_inner._decode_bc3(solid_block)  # type: ignore[attr-defined]
    ):
        raise FamilyLayoutError("controlled BC3 solid is not lossless")

    shoulders: list[dict[str, object]] = []
    reference_descriptor = None
    reference_layout = None
    with apf_inner.ArchiveReader(archive) as reader:
        for asset_index in range(24):
            entry = by_id.get(outer_id(f"uniform_shoulder_{asset_index:02d}.iff"))
            normal = by_id.get(
                outer_id(f"uniform_shoulder_normal_{asset_index:02d}.iff")
            )
            if entry is None or normal is None:
                raise FamilyLayoutError(f"missing shoulder pair {asset_index:02d}")
            row, descriptor, layout = _analyze(
                reader,
                entry,
                normal,
                asset_index,
                uses[asset_index],
                solid_block,
                reference_descriptor,
                reference_layout,
            )
            if reference_descriptor is None:
                reference_descriptor, reference_layout = descriptor, layout
            shoulders.append(row)
    after = index_path.stat()
    after_hash = sha256_file(index_path)
    # ``before`` and ``after`` are both index_path.stat() -- two PATH stats of
    # one pathname, which agree on st_ctime_ns on every platform.  No path/fd
    # boundary is crossed, so the change time stays compared.  NOTE: this tuple
    # carries no st_dev/st_ino; identity comes from the SHA-256 above.
    if (
        after_hash != EXPECTED_VOLUME_SHA256
        or (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        != (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    ):
        raise FamilyLayoutError("source volume changed during read-only audit")
    assert reference_descriptor is not None and reference_layout is not None
    used = [index for index, value in uses.items() if value]
    unused = [index for index, value in uses.items() if not value]
    shared = [index for index, value in uses.items() if len(value) > 1]
    minimum = min(
        row["controlled_solid_rebuild_in_memory"]["iff"]["allocation_slack_after"]  # type: ignore[index]
        for row in shoulders
    )
    return {
        "schema": SCHEMA,
        "scope": {
            "game": "All-Pro Football 2K8 (USA)",
            "family": "uniform_shoulder",
            "asset_indices": list(range(24)),
            "inner_file_index": transport.INNER_INDEX,
            "inner_name": transport.INNER_NAME,
            "paired_family": "uniform_shoulder_normal",
        },
        "source": {
            "volume": "0A",
            "size": before.st_size,
            "sha256_before": EXPECTED_VOLUME_SHA256,
            "sha256_after": after_hash,
            "size_mtime_ctime_unchanged": True,
            "opened_for_write": False,
            "copied_volume_used": False,
        },
        "family_equivalence": {
            "package_count": 24,
            "paired_normal_package_count": 24,
            "all_24_color_and_normal_names_resolved_by_outer_crc": True,
            "all_complete_color_txtr_descriptors_identical": True,
            "all_iff_structures_two_blocks_four_files": True,
            "all_h7a_shift_profiles_9_9": True,
            "all_nine_level_layouts_identical": True,
            "all_retail_transports_bit_exact": True,
            "all_controlled_solid_rebuilds_fit_fixed_allocations": True,
            "all_three_sibling_textures_preserved": True,
            "minimum_controlled_allocation_slack": minimum,
            "canonical_txtr_descriptor": reference_descriptor,
            "canonical_nine_level_layout": reference_layout,
        },
        "selector_sharing": {
            "inventory_path": "reports/assets/apf_uniform_inventory.json",
            "inventory_sha256": EXPECTED_INVENTORY_SHA256,
            "selector_slot": 11,
            "selected_families": ["shoulder", "shoulder_normal"],
            "one_asset_index_selects_both_paired_packages": True,
            "team_count": 40,
            "banks_per_team": 2,
            "team_bank_use_count": 80,
            "used_asset_indices": used,
            "unused_asset_indices": unused,
            "shared_asset_indices": shared,
            "asset_use_counts": {str(index): len(uses[index]) for index in range(24)},
            "editing_one_color_asset_affects_every_listed_team_bank_use": True,
            "selector_records_or_roster_written": False,
        },
        "controlled_fixture": {
            "description": "RGBA-exact magenta BC3; contains no retail pixels",
            "rgba": list(SOLID_RGBA),
            "bc3_block_sha256": sha256(solid_block),
            "bc3_block_decode_exact": True,
            "replacement_bytes_embedded": False,
        },
        "shoulders": shoulders,
        "claim_boundary": {
            "structural_layout_generalizes_across_all_24_shoulders": True,
            "in_memory_transport_and_fixed_allocation_rebuild_proved_for_all_24": True,
            "team_selector_sharing_enumerated": True,
            "paired_normal_packages_physically_separate_and_preserved": True,
            "runtime_visibility_proved": False,
            "xenia_rendering_proved": False,
            "xbox_360_hardware_rendering_proved": False,
            "production_quality_bc3_encoder_proved": False,
            "retail_or_copied_game_volume_written": False,
        },
        "portme": [
            "Capture representative changed shoulders for both banks in Xenia and on hardware.",
            "Replace the bounded proof BC3 encoder with a production perceptual backend.",
            "Treat every listed team/bank use as affected when editing a shared asset.",
            "Keep shoulder-normal authoring separate until its two-channel semantics are mapped.",
        ],
    }


def write_tsv(path: Path, report: dict[str, object]) -> None:
    columns = [
        "asset_index",
        "outer_name",
        "outer_table_index",
        "pack_offset",
        "allocation_size",
        "allocation_sha256",
        "texture_sha256",
        "paired_normal_outer_table_index",
        "paired_normal_allocation_sha256",
        "team_bank_use_count",
        "team_bank_uses",
        "controlled_allocation_slack",
        "retail_transport_bit_exact",
        "three_sibling_textures_preserved",
        "entry_or_volume_written",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in report["shoulders"]:  # type: ignore[index]
            writer.writerow(
                {
                    "asset_index": row["asset_index"],
                    "outer_name": row["outer_name"],
                    "outer_table_index": row["outer_table_index"],
                    "pack_offset": hx(row["physical"]["pack_offset"]),
                    "allocation_size": row["outer_allocation"]["size"],
                    "allocation_sha256": row["outer_allocation"]["sha256"],
                    "texture_sha256": row["inner_file"]["texture_sha256"],
                    "paired_normal_outer_table_index": row["paired_normal_package"]["outer_table_index"],
                    "paired_normal_allocation_sha256": row["paired_normal_package"]["allocation_sha256"],
                    "team_bank_use_count": row["team_bank_use_count"],
                    "team_bank_uses": ",".join(
                        f"{use['team_index']}:{use['bank']}"
                        for use in row["team_bank_uses"]
                    ),
                    "controlled_allocation_slack": row["controlled_solid_rebuild_in_memory"]["iff"]["allocation_slack_after"],
                    "retail_transport_bit_exact": "true",
                    "three_sibling_textures_preserved": "true",
                    "entry_or_volume_written": "false",
                }
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--tsv", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = analyze(args.index)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        write_tsv(args.tsv, report)
        print(
            "APF_SHOULDER_FAMILY_LAYOUT_PASS packages=24 paired_normals=24 "
            "levels=9 retail_written=false runtime_visibility=false"
        )
    except (
        FamilyLayoutError,
        transport.ShoulderTransportError,
        xenos_mips.MipLayoutError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
