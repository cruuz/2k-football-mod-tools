#!/usr/bin/env python3
"""Audit all 24 APF helmet-color packages and selector sharing read-only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import zlib

from PIL import Image

import apf_helmet_color_transport as transport
import apf_inner
import apf_outer
import apf_xenos_dxn_mip_layout as dxn_mips


def change_time_identity(info: os.stat_result) -> tuple[int, ...]:
    """``(info.st_ctime_ns,)`` on POSIX; ``()`` on Windows.

    Inlined rather than imported from
    :mod:`mod_editor.core.platform_compat` because this module is executed as a
    self-contained, tools-only closure and may not import the editor package;
    the contract is byte-for-byte that helper's.

    On Windows a path stat and an fd stat of the *same, untouched* file do not
    agree on ``st_ctime``, so putting it in an identity tuple refuses a file
    nothing touched.  ``st_dev``/``st_ino`` stay the identity and
    ``st_size``/``st_mtime_ns`` stay the change detectors, so a swapped or
    rewritten file is still caught.  What is genuinely lost on Windows is the
    metadata-only-change signal -- a permission or attribute edit that leaves
    the bytes, the size and the modification time untouched -- and Windows
    offers no equivalent field that is stable across the two calls, so this
    check is weaker there than on POSIX.  Stated, not hidden.
    """

    if sys.platform.startswith("win"):
        return ()
    return (info.st_ctime_ns,)


SCHEMA = "apf_helmet_family_layout/v1"
EXPECTED_VOLUME_SIZE = 1_140_850_688
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
EXPECTED_INVENTORY_SHA256 = "b3ad0e44af0163b30857e20c7c4e90ceb89cbc3dbc8cc41508fce3aaf1c136c7"
WORKSPACE = Path(__file__).resolve().parents[1]
INVENTORY = WORKSPACE / "reports/assets/apf_uniform_inventory.json"
CONTROL_RGBA = (255, 0, 0, 255)


class FamilyLayoutError(ValueError):
    """Raised when retail helmet evidence differs from the proved class."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def hx(value: int) -> str:
    return f"0x{value:08x}"


def outer_id(name: str) -> int:
    return zlib.crc32(name.upper().encode("ascii")) & 0xFFFFFFFF


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _selector_uses() -> dict[int, list[dict[str, object]]]:
    payload = INVENTORY.read_bytes()
    if sha256(payload) != EXPECTED_INVENTORY_SHA256:
        raise FamilyLayoutError("APF uniform inventory hash changed")
    inventory = json.loads(payload)
    if (inventory["source"]["archive_index"] !=
            "extracted/All-Pro Football 2K8 (USA)/0A" or
            inventory["source"]["archive_volume_sizes"]["0A"] != EXPECTED_VOLUME_SIZE):
        raise FamilyLayoutError("uniform inventory source identity changed")
    result = {index: [] for index in range(24)}
    teams = inventory["team_selector_graph"]["teams"]
    if len(teams) != 40:
        raise FamilyLayoutError("uniform team roster changed")
    for team in teams:
        if [bank["bank"] for bank in team["banks"]] != [0, 1]:
            raise FamilyLayoutError("uniform bank roster changed")
        for bank in team["banks"]:
            selector = bank["selectors"][3]
            if (selector["slot"] != 3 or selector["families"] != ["helmet"] or
                    selector["semantic_status"] !=
                    "filename selector proved by XEX 0x849D6BD0"):
                raise FamilyLayoutError("helmet selector ownership changed")
            asset = selector["asset_index_byte_0"]
            if type(asset) is not int or asset not in result:
                raise FamilyLayoutError("helmet asset index is out of range")
            result[asset].append({
                "team_index": team["team_index"],
                "team_name": team["display_name"],
                "abbreviation": team["abbreviation"],
                "slot_kind": team["slot_kind"],
                "bank": bank["bank"],
                "selector_record_index": selector["selector_record_index"],
                "selector_record_offset": selector["selector_record_offset"],
            })
    if sum(map(len, result.values())) != 80:
        raise FamilyLayoutError("helmet selector graph no longer has 80 uses")
    return result


def _block_row(block: apf_inner.Block, stored: bytes, decoded: bytes) -> dict[str, object]:
    return {
        "index": block.descriptor_index,
        "start_offset": block.start_offset,
        "uncompressed_length": block.uncompressed_length,
        "stored_length": block.stored_length,
        "stored_sha256": sha256(stored),
        "decoded_sha256": sha256(decoded),
        "is_h7a_compressed": block.is_compressed,
        "h7a_shift": block.wrapper.shift if block.wrapper else None,
    }


def analyze(index_path: Path) -> dict[str, object]:
    index_path = index_path.expanduser().resolve(strict=True)
    before = index_path.stat()
    if before.st_size != EXPECTED_VOLUME_SIZE or sha256_file(index_path) != EXPECTED_VOLUME_SHA256:
        raise FamilyLayoutError("source is not pinned retail APF 2K8 0A")
    uses = _selector_uses()
    archive = apf_outer.parse_archive(index_path)
    by_id = {entry.name_id: entry for entry in archive.entries}
    if len(by_id) != len(archive.entries):
        raise FamilyLayoutError("duplicate outer name IDs")
    wanted_base = Image.new("RGBA", (256, 1024), CONTROL_RGBA).tobytes()
    helmets = []
    reference_descriptor = None
    reference_layout = None
    with apf_inner.ArchiveReader(archive) as reader:
        for asset_index in range(24):
            name = f"uniform_helmet_{asset_index:02d}.iff"
            entry = by_id.get(outer_id(name))
            if entry is None or len(entry.segments) != 1 or entry.segments[0].pack_name != "0A":
                raise FamilyLayoutError(f"{name}: missing one-segment 0A entry")
            record = apf_inner.parse_iff(reader, entry)
            original_entry = reader.read(entry, 0, entry.size)
            blocks = [apf_inner.decode_block(reader, record, index, 1 << 30)
                      for index in range(record.block_count)]
            stored = [reader.read(entry, block.start_offset, block.stored_length)
                      for block in record.blocks]
            descriptor, texture = transport._validate_structure(record, blocks)  # type: ignore[attr-defined]
            locations = dxn_mips.derive_layout(descriptor)
            layout = [item.manifest() for item in locations]
            if reference_descriptor is not None and canonical(descriptor) != canonical(reference_descriptor):
                raise FamilyLayoutError(f"{name}: complete descriptor drift")
            if reference_layout is not None and canonical(layout) != canonical(reference_layout):
                raise FamilyLayoutError(f"{name}: mip layout drift")
            if len(locations) != 7 or [(x.level, x.origin_block_x, x.origin_block_y)
                                       for x in locations[4:]] != [(4, 4, 0), (5, 2, 0), (6, 1, 0)]:
                raise FamilyLayoutError(f"{name}: packed-tail layout drift")
            if dxn_mips.transport_roundtrip(texture, locations) != texture:
                raise FamilyLayoutError(f"{name}: retail DXN transport failed")
            linear = [dxn_mips.extract_linear_dxn(texture, item) for item in locations]
            rgba = [transport.decode_linear_dxn(value, item)
                    for value, item in zip(linear, locations)]
            wanted = [wanted_base] + [
                Image.frombytes("RGBA", (256, 1024), wanted_base).resize(
                    (item.width, item.height), Image.Resampling.BOX
                ).tobytes() for item in locations[1:]
            ]
            changed_texture = texture
            changed_counts = []
            for item, old_linear, old_rgba, desired in zip(locations, linear, rgba, wanted):
                new_linear, indices, _ = transport._encode_changed_blocks(  # type: ignore[attr-defined]
                    old_linear, old_rgba, desired, item
                )
                changed_texture = dxn_mips.insert_linear_dxn(changed_texture, item, new_linear)
                changed_counts.append(len(indices))
            mask = transport.active_byte_mask(len(texture), locations)
            if transport.hash_inactive(texture, mask) != transport.hash_inactive(changed_texture, mask):
                raise FamilyLayoutError(f"{name}: controlled rebuild changed padding")
            rebuilt, iff = transport._rebuild_entry(  # type: ignore[attr-defined]
                entry, record, original_entry, blocks, stored, changed_texture
            )
            if len(rebuilt) != entry.size or not iff["helmet_normal_preserved"]:
                raise FamilyLayoutError(f"{name}: fixed rebuild/preservation failed")
            if record.footer is None:
                raise FamilyLayoutError(f"{name}: missing footer")
            footer_size = 8 + record.footer.payload_size
            tail = original_entry[record.file_length + footer_size:]
            if any(tail):
                raise FamilyLayoutError(f"{name}: nonzero allocation tail")
            color = record.files[0]
            normal = record.files[1]
            row = {
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
                    "blocks": [_block_row(block, raw, decoded)
                               for block, raw, decoded in zip(record.blocks, stored, blocks)],
                    "file_names": [item.name for item in record.files],
                    "footer_sha256": sha256(original_entry[
                        record.file_length:record.file_length + footer_size
                    ]),
                },
                "inner_file": {
                    "index": color.index,
                    "name": color.name,
                    "type_name": color.type_name,
                    "parts": [{
                        "part_index": index,
                        "block_index": part.block_index,
                        "offset": part.offset,
                        "length": part.length,
                        "sha256": sha256(blocks[part.block_index][part.offset:part.offset + part.length]),
                    } for index, part in enumerate(color.parts)],
                    "texture_sha256": sha256(texture),
                },
                "preserved_normal_file": {
                    "index": normal.index,
                    "name": normal.name,
                    "parts": [{
                        "part_index": index,
                        "block_index": part.block_index,
                        "offset": part.offset,
                        "length": part.length,
                        "sha256": sha256(blocks[part.block_index][part.offset:part.offset + part.length]),
                    } for index, part in enumerate(normal.parts)],
                },
                "txtr_descriptor": descriptor,
                "seven_level_layout": [{**item.manifest(),
                                          "linear_dxn_sha256": sha256(level)}
                                         for item, level in zip(locations, linear)],
                "team_bank_use_count": len(uses[asset_index]),
                "team_bank_uses": uses[asset_index],
                "controlled_two_channel_rebuild_in_memory": {
                    "rgba": list(CONTROL_RGBA),
                    "png_contract": "R/G are DXN channels; B=0; A=255",
                    "changed_block_counts": changed_counts,
                    "inactive_padding_bit_exact": True,
                    "transport_bit_exact": dxn_mips.transport_roundtrip(changed_texture, locations) == changed_texture,
                    "rebuilt_entry_length": len(rebuilt),
                    "rebuilt_entry_sha256": sha256(rebuilt),
                    "fixed_outer_allocation": True,
                    "iff": iff,
                    "entry_or_volume_written": False,
                },
            }
            helmets.append(row)
            if reference_descriptor is None:
                reference_descriptor, reference_layout = descriptor, layout
    after = index_path.stat()
    after_hash = sha256_file(index_path)
    if (after_hash != EXPECTED_VOLUME_SHA256 or
            (after.st_size, after.st_mtime_ns, *change_time_identity(after)) !=
            (before.st_size, before.st_mtime_ns, *change_time_identity(before))):
        raise FamilyLayoutError("source volume changed during read-only audit")
    assert reference_descriptor is not None and reference_layout is not None
    used = [index for index in range(24) if uses[index]]
    return {
        "schema": SCHEMA,
        "scope": {
            "game": "All-Pro Football 2K8 (USA)",
            "family": "uniform_helmet",
            "asset_indices": list(range(24)),
            "inner_file_index": 0,
            "inner_name": "helmet_color",
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
            "all_24_names_resolved_by_outer_crc": True,
            "all_complete_txtr_descriptors_identical": True,
            "all_iff_structures_two_blocks_two_files": True,
            "all_h7a_shift_profiles_pinned": True,
            "h7a_shift_profile_counts": {
                "8,10": sum([block["h7a_shift"] for block in row["iff"]["blocks"]] == [8, 10]
                            for row in helmets)
            },
            "all_seven_level_layouts_identical": True,
            "all_retail_transports_bit_exact": True,
            "all_controlled_two_channel_rebuilds_fit_fixed_allocations": True,
            "all_helmet_normal_files_preserved": True,
            "minimum_controlled_allocation_slack": min(
                row["controlled_two_channel_rebuild_in_memory"]["iff"]["allocation_slack_after"]
                for row in helmets
            ),
            "canonical_txtr_descriptor": reference_descriptor,
            "canonical_seven_level_layout": reference_layout,
        },
        "selector_sharing": {
            "inventory_path": "reports/assets/apf_uniform_inventory.json",
            "inventory_sha256": EXPECTED_INVENTORY_SHA256,
            "selector_slot": 3,
            "team_count": 40,
            "banks_per_team": 2,
            "team_bank_use_count": 80,
            "used_asset_indices": used,
            "unused_asset_indices": [index for index in range(24) if not uses[index]],
            "shared_asset_indices": [index for index in range(24) if len(uses[index]) > 1],
            "asset_use_counts": {str(index): len(uses[index]) for index in range(24)},
            "editing_one_asset_affects_every_listed_team_bank_use": True,
            "selector_records_or_roster_written": False,
        },
        "controlled_fixture": {
            "description": "two-channel exact red (R=255,G=0,B=0,A=255); no retail pixels",
            "rgba": list(CONTROL_RGBA),
            "png_contract": "R/G are DXN channels; B=0; A=255",
            "replacement_bytes_embedded": False,
        },
        "helmets": helmets,
        "claim_boundary": {
            "structural_layout_generalizes_across_all_24_helmets": True,
            "in_memory_transport_and_fixed_allocation_rebuild_proved_for_all_24": True,
            "team_selector_sharing_enumerated": True,
            "helmet_normal_preservation_proved_for_all_24": True,
            "helmet_color_channel_meanings_named": False,
            "runtime_visibility_proved": False,
            "xenia_rendering_proved": False,
            "xbox_360_hardware_rendering_proved": False,
            "production_quality_dxn_encoder_proved": False,
            "retail_or_copied_game_volume_written": False,
        },
        "portme": [
            "Name both helmet_color channels from shader/runtime evidence.",
            "Capture representative changed helmets in Xenia and on hardware.",
            "Replace the bounded BC4-pair encoder with a production perceptual backend.",
            "Treat every listed team/bank use as affected when editing a shared asset.",
        ],
    }


def write_tsv(path: Path, report: dict[str, object]) -> None:
    fields = [
        "asset_index", "outer_name", "outer_table_index", "pack_offset",
        "allocation_size", "allocation_sha256", "texture_sha256",
        "team_bank_use_count", "team_bank_uses", "controlled_allocation_slack",
        "retail_transport_bit_exact", "helmet_normal_preserved",
        "entry_or_volume_written",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in report["helmets"]:  # type: ignore[index]
            writer.writerow({
                "asset_index": row["asset_index"],
                "outer_name": row["outer_name"],
                "outer_table_index": row["outer_table_index"],
                "pack_offset": hx(row["physical"]["pack_offset"]),
                "allocation_size": row["outer_allocation"]["size"],
                "allocation_sha256": row["outer_allocation"]["sha256"],
                "texture_sha256": row["inner_file"]["texture_sha256"],
                "team_bank_use_count": row["team_bank_use_count"],
                "team_bank_uses": ",".join(
                    f"{use['team_index']}:{use['bank']}" for use in row["team_bank_uses"]
                ),
                "controlled_allocation_slack": row["controlled_two_channel_rebuild_in_memory"]["iff"]["allocation_slack_after"],
                "retail_transport_bit_exact": "true",
                "helmet_normal_preserved": "true",
                "entry_or_volume_written": "false",
            })


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
            "APF_HELMET_FAMILY_LAYOUT_PASS packages=24 levels=7 "
            f"used={len(report['selector_sharing']['used_asset_indices'])} "  # type: ignore[index]
            "retail_written=false runtime_visibility=false"
        )
    except (FamilyLayoutError, transport.HelmetTransportError,
            dxn_mips.MipLayoutError, apf_inner.FormatError,
            apf_outer.FormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
