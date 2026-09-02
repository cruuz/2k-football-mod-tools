#!/usr/bin/env python3
"""Inventory the standalone TXTR targets the editor can replace.

These are the textures modders kept asking for and finding absent: the real
teams' end-zone art, the stadium goalpost pads, ``divots``, the ``mark*``
overlays laid over the grass, the shared equipment textures, and the four
presentation textures carried separately by every uniform package.  The last
group is intentionally distinct from the live helmet/jersey art and from the
pre-rendered Team Select uniform/helmet cards.

They are deliberately **not** the Stadium Studio corpus.  That lane replays the
strict SCNE parser and edits textures *embedded inside* a scene; these are
standalone ``TXTR`` chunks sitting alongside those scenes in the same outer
package -- outer 3136 for example carries five SCNE chunks and eight separate
TXTRs.  The two sets do not overlap.

Only a texture whose retail layout matches a proved writer contract is listed:
compressed swizzled P8 with its complete palette layout, or one of the twelve
explicit-size A1R5G5B5 player-strip names whose five linear mip levels and
source-owned video tail have been measured across all 340 packages. Anything
else is reported as skipped with its reason, so the count is never quietly
smaller than it looks.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib

import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from nfl_outer import parse_archive, read_entry_bytes
from nfl_txtr import HEADER, decode_chunk, parse_chunks, parse_texture


SCHEMA = "nfl2k5_p8_texture_inventory/v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
DEFAULT_JSON = ROOT / "reports/assets/nfl2k5_p8_texture_inventory.json"
DEFAULT_TEAM_SELECT_INVENTORY = (
    ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json"
)
# Retail sectors, recorded for the build proof only. A pressed disc or a
# repack puts the same pack somewhere else, so the build locates it by path
# and re-derives every offset; nothing compares against these.
RETAIL_PACK_SECTORS = {
    "0": 796_479,
    "1": 649_995,
    "2": 891_064,
    "3": 495_938,
    "4": 1_042_066,
    "8": 1_574_589,
    "9": 35_531,
    "A": 2_403_082,
    "B": 2_179_328,
    "C": 2_554_593,
}

# The families this workspace claims, and the label each carries in the browser.
# Every entry is a texture name that exists in a standalone TXTR chunk.
FAMILIES: dict[str, tuple[str, str]] = {
    "endzone_north_left": ("End Zone", "End Zone North — Left"),
    "endzone_north_middle": ("End Zone", "End Zone North — Middle"),
    "endzone_north_right": ("End Zone", "End Zone North — Right"),
    "endzone_south_left": ("End Zone", "End Zone South — Left"),
    "endzone_south_middle": ("End Zone", "End Zone South — Middle"),
    "endzone_south_right": ("End Zone", "End Zone South — Right"),
    "pad_north": ("Goalpost Pads", "Goalpost Pad — North"),
    "pad_south": ("Goalpost Pads", "Goalpost Pad — South"),
    "divots": ("Field Surface", "Grass Divots Overlay"),
    "shoes_taped": ("Equipment", "Shoes — Taped"),
    "wristband_qb": ("Equipment", "Wristband — Quarterback"),
    "elbowpad_taped": ("Equipment", "Elbow Pad — Taped"),
    "elbowpad_rubber": ("Equipment", "Elbow Pad — Rubber"),
    "elbowpad_elastic": ("Equipment", "Elbow Pad — Elastic"),
    # Every one of the 634 uniform packages owns these four standalone P8
    # resources in chunks 49..52.  The XBE contains direct ``logo`` and
    # ``zteam1chiclet`` lookups, but a complete screen-by-screen consumer map
    # is not proved, so the product calls the family "Team Presentation"
    # instead of claiming one specific menu.  They are still separate bytes
    # from both the live helmet diffuse and the Team Select card rasters.
    "logo": ("Team Presentation — Menu / UI", "Team Logo — Presentation"),
    "chiclet": ("Team Presentation — Menu / UI", "Team Chiclet"),
    "splayer": ("Team Presentation — Menu / UI", "Team Player Banner"),
    "flipchip": ("Team Presentation — Menu / UI", "Team Flip Chip"),
}
PRESENTATION_NAMES = frozenset({"logo", "chiclet", "splayer", "flipchip"})
PLAYER_STRIP_NAMES = frozenset({
    "p001", "p002", "p003", "p004", "p005", "p006",
    "p011", "p012", "p013", "p014", "p015", "p016",
})

# Team-facing presentation atlases which are separate from both the live
# uniform packages and the three large Team Select cards.  Their exact outer
# identities are CRC32(uppercase UTF-16LE filename), just like every other NFL
# 2K5 archive name.  Keep this list bounded: the two ``unknown_[ha]`` mini.cdf
# slots and unrelated stadium/office art are intentionally not inferred into
# the product merely because they live nearby.
MENU_AGGREGATE_SPECS = {
    3_096: {
        "outer_name": "flipchip.cdf",
        "outer_id": 0xF50B1A31,
        "outer_size": 1_704_192,
        "pattern": re.compile(r"^(?P<code>[0-9]{2})_flipchip_00_h(?P<style>[0-9]+)$"),
        "count": 317,
        "width": 64,
        "height": 64,
        "family": "menu_flipchip",
        "group": "Team Logos — Menus / Presentation",
        "label": "Team Flip Chip — Shared Menu",
    },
    3_102: {
        "outer_name": "logos.cdf",
        "outer_id": 0x823E3053,
        "outer_size": 105_903_360,
        "pattern": re.compile(r"^logo_(?P<code>[0-9]{2})_(?P<style>[0-9]+)$"),
        "count": 317,
        "width": 256,
        "height": 256,
        "family": "menu_logo_large",
        "group": "Team Logos — Menus / Presentation",
        "label": "Team Logo — Full Menu",
    },
    3_103: {
        "outer_name": "mini.cdf",
        "outer_id": 0x48F8908C,
        "outer_size": 5_123_328,
        "patterns": (
            {
                "pattern": re.compile(
                    r"^logo_s(?P<code>[0-9]{2})_(?P<style>[0-9]+)$"
                ),
                "count": 317,
                "family": "menu_logo_small",
                "group": "Team Logos — Menus / Presentation",
                "label": "Team Logo — Compact Menu",
            },
            {
                "pattern": re.compile(
                    r"^mini_(?P<side>[ha])(?P<code>[0-9]{2})_(?P<style>[0-9]+)$"
                ),
                "count": 634,
                "family": "menu_mini_card",
                "group": "Team Mini Cards — Menus / Presentation",
                "label": "Team Mini Card",
            },
        ),
        "width": 64,
        "height": 64,
    },
}

FRANCHISE_ASSET_CODES = tuple(
    [f"{value:02d}" for value in range(0, 32)]
    + [f"{value:02d}" for value in range(33, 38)]
    + [f"{value:02d}" for value in range(40, 47)]
    + [f"{value:02d}" for value in range(50, 86)]
    + [f"{value:02d}" for value in range(95, 100)]
)
MENU_PRESENTATION_FAMILIES = frozenset({
    "menu_logo_large",
    "menu_logo_small",
    "menu_flipchip",
    "menu_mini_card",
    "franchise_team_logo",
    "draft_pda_logo",
})
for _strip_name in sorted(PLAYER_STRIP_NAMES):
    FAMILIES[_strip_name] = (
        "Player Presentation Strips",
        f"Player Strip {_strip_name[1:]}",
    )


class InventoryError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InventoryError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def eligible(info, chunk) -> str | None:
    """Return None when the writer's contract holds, else why it does not."""
    if info.format_name == "A1R5G5B5" and info.name in PLAYER_STRIP_NAMES:
        if info.packed_size == 0:
            return "A1 player strip is not explicit-size"
        if info.pixel_offset != 0 or info.palette_offset != 0:
            return "A1 player strip offsets changed"
        if info.dimensions != 2 or info.depth != 1 or info.mip_levels != 5:
            return "A1 player strip descriptor shape changed"
        chain = sum(
            max(1, info.width >> level) * max(1, info.height >> level) * 2
            for level in range(info.mip_levels)
        )
        if chain > chunk.video_bytes:
            return "A1 player strip mip chain runs past the video buffer"
        if chunk.video_bytes - chain != (info.width * 3) // 2:
            return "A1 player strip source-owned video tail changed"
        return None
    if info.format_name != "P8":
        return f"format {info.format_name}"
    if info.packed_size != 0:
        return "linear pixels"
    if info.pixel_offset != 0:
        return "index chain does not start the video buffer"
    levels = info.mip_levels or 1
    chain = sum(
        max(1, info.width >> level) * max(1, info.height >> level)
        for level in range(levels)
    )
    if info.palette_offset != chain:
        return "palette does not follow a complete mip chain"
    if info.palette_offset + 1024 > chunk.video_bytes:
        return "palette runs past the video buffer"
    return None


def _pack_records(index_path: Path, targets: list[dict[str, object]]) \
        -> dict[str, dict[str, object]]:
    """Hash each pack reached by *targets* and retain its copy-build identity."""

    packs: dict[str, dict[str, object]] = {}
    names: set[str] = set()
    for row in targets:
        physical_spans = row.get("physical_spans")
        if isinstance(physical_spans, list):
            names.update(str(piece["pack_name"]) for piece in physical_spans)
        else:
            names.add(str(row["pack_name"]))
    for name in sorted(names):
        pack_path = index_path.parent / name
        if not pack_path.is_file():
            pack_path = index_path.parent / name.upper()
        require(pack_path.is_file(), f"pack {name} is missing beside the index")
        require(name in RETAIL_PACK_SECTORS,
                f"pack {name} has no recorded retail-sector witness")
        hasher = hashlib.sha256()
        with pack_path.open("rb") as stream:
            for block in iter(lambda: stream.read(16 << 20), b""):
                hasher.update(block)
        packs[name] = {
            "path": f"vc_53450030/{name}",
            "retail_sector": RETAIL_PACK_SECTORS[name],
            "sha256": hasher.hexdigest(),
            "size": pack_path.stat().st_size,
        }
    return packs


def _owning_segment(entry, offset: int, size: int):
    """Return the one physical pack extent containing an entry-relative span."""

    logical_start = 0
    for segment in entry.segments:
        logical_end = logical_start + segment.size
        if logical_start <= offset and offset + size <= logical_end:
            return segment, offset - logical_start
        logical_start = logical_end
    return None


def _physical_span_records(entry, offset: int, payload: bytes) \
        -> list[dict[str, object]]:
    """Describe every ordered physical slice of one logical TXTR span."""

    result: list[dict[str, object]] = []
    logical_start = 0
    replacement_offset = 0
    range_end = offset + len(payload)
    for segment in entry.segments:
        logical_end = logical_start + segment.size
        part_start = max(offset, logical_start)
        part_end = min(range_end, logical_end)
        if part_start < part_end:
            size = part_end - part_start
            piece = payload[replacement_offset:replacement_offset + size]
            require(len(piece) == size, "TXTR physical split is incomplete")
            result.append({
                "pack_name": segment.pack_name,
                "pack_relative_offset": (
                    segment.pack_offset + part_start - logical_start
                ),
                "replacement_offset": replacement_offset,
                "size": size,
                "span_sha256": digest(piece),
            })
            replacement_offset += size
        logical_start = logical_end
        if part_end == range_end:
            break
    require(result and replacement_offset == len(payload),
            "TXTR span could not be mapped across physical packs")
    require(len(result) <= 2,
            "TXTR span reaches more than two physical packs")
    return result


def _uniform_presentation_metadata(
    path: Path = DEFAULT_TEAM_SELECT_INVENTORY,
) -> dict[int, dict[str, object]]:
    """Safe team/set labels keyed by the uniform package's canonical name ID."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read Team Select labels: {exc}") from exc
    targets = document.get("targets") or []
    require(
        document.get("schema") == "nfl2k5_team_select_card_inventory/v1"
        and isinstance(targets, list)
        and len(targets) == 1_902,
        "Team Select label source changed",
    )
    result: dict[int, dict[str, object]] = {}
    for row in targets:
        logical = str(row["uniform_package"])
        require(logical.endswith(".IFF"),
                f"Team Select row has an invalid uniform package: {logical}")
        name_id = zlib.crc32(logical.upper().encode("utf-16le")) & 0xFFFFFFFF
        metadata = {
            "set_selector": logical[:-4],
            "style_display": str(row["style_display"]),
            "team_abbreviations": str(row["team_abbreviations"]),
            "team_names": str(row["team_names"]),
            "historic_abbreviations": str(row["historic_abbreviations"]),
        }
        previous = result.setdefault(name_id, metadata)
        require(previous == metadata,
                f"Team Select labels disagree for {logical}")
    require(len(result) == 634, "Team Select uniform-package IDs are duplicated")
    return result


def _team_style_metadata(
    path: Path = DEFAULT_TEAM_SELECT_INVENTORY,
) -> tuple[
    dict[tuple[str, int], dict[str, object]],
    dict[str, dict[str, object]],
]:
    """Join aggregate menu assets to the already-reviewed team/style domain.

    The Team Select report has six concrete rows per logical team/style key:
    HOME/AWAY uniform cards plus HOME/AWAY 256- and 128-pixel helmet cards.
    Aggregate menu logos and flipchips deliberately collapse that side axis;
    mini cards retain it.  This function proves that relationship instead of
    guessing labels from the texture name.
    """

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read Team Select labels: {exc}") from exc
    targets = document.get("targets") or []
    require(
        document.get("schema") == "nfl2k5_team_select_card_inventory/v1"
        and isinstance(targets, list)
        and len(targets) == 1_902,
        "Team Select label source changed",
    )
    buckets: dict[tuple[str, int], list[dict[str, object]]] = {}
    for raw in targets:
        require(isinstance(raw, dict), "Team Select label row is not an object")
        code = str(raw["asset_code"])
        style = int(raw["style"])
        buckets.setdefault((code, style), []).append(raw)
    require(len(buckets) == 317, "Team Select logical team/style count changed")

    logical: dict[tuple[str, int], dict[str, object]] = {}
    teams: dict[str, dict[str, object]] = {}
    for key, rows in buckets.items():
        code, style = key
        require(len(rows) == 6, f"Team Select {code} style {style} has no six-row join")
        for field in (
            "team_names",
            "team_abbreviations",
            "historic_abbreviations",
            "style_display",
        ):
            require(
                len({str(row[field]) for row in rows}) == 1,
                f"Team Select {code} style {style} disagrees on {field}",
            )
        packages: dict[str, str] = {}
        for side in ("H", "A"):
            names = {
                str(row["uniform_package"])
                for row in rows if str(row["side_code"]).upper() == side
            }
            require(
                names == {f"{code}{side}{style}.IFF"},
                f"Team Select {code} style {style} {side} package join changed",
            )
            packages[side] = next(iter(names))[:-4]
        metadata: dict[str, object] = {
            "asset_code": code,
            "style": style,
            "style_display": str(rows[0]["style_display"]),
            "team_abbreviations": str(rows[0]["team_abbreviations"]),
            "team_names": str(rows[0]["team_names"]),
            "historic_abbreviations": str(rows[0]["historic_abbreviations"]),
            "set_selectors": [packages["H"], packages["A"]],
        }
        logical[key] = metadata
        team_metadata = {
            field: metadata[field] for field in (
                "asset_code",
                "team_abbreviations",
                "team_names",
                "historic_abbreviations",
            )
        }
        previous = teams.setdefault(code, team_metadata)
        require(previous == team_metadata, f"Team Select team labels disagree for {code}")
    require(len(teams) == 85, "Team Select asset-code count changed")
    return logical, teams


def build(index_path: Path) -> dict[str, object]:
    archive = parse_archive(index_path)
    presentation_metadata = _uniform_presentation_metadata()
    targets: list[dict[str, object]] = []
    skipped: Counter[str] = Counter()
    for outer_index, entry in enumerate(archive.entries):
        # The original families were deliberately restricted to single-extent
        # outers. Uniform packages can cross an internal pack boundary, but
        # their four presentation TXTRs are each wholly contained by one
        # physical extent and can therefore use the same exact-span writer.
        if len(entry.segments) != 1 and not any(
            marker in (entry.head_ascii or "") for marker in ("Unif", "AUDO")
        ):
            continue
        head = entry.head_ascii or ""
        if not any(
            marker in head for marker in ("TXTR", "SCNE", "Unif", "AUDO", "FONT")
        ):
            # cheap pre-filter; packages with no resource head cannot carry one
            continue
        try:
            data = read_entry_bytes(archive, entry)
            chunks = parse_chunks(data, allow_trailing=True)
        except Exception:  # noqa: BLE001 - an unreadable package is simply skipped
            continue
        if not any(chunk.kind == "TXTR" for chunk in chunks):
            continue
        for position, chunk in enumerate(chunks):
            if chunk.kind != "TXTR":
                continue
            try:
                decoded, _info = decode_chunk(data, chunk)
                info = parse_texture(decoded, chunk)
            except Exception:  # noqa: BLE001
                continue
            if info.name not in FAMILIES:
                continue
            reason = eligible(info, chunk)
            if reason is not None:
                skipped[f"{info.name}: {reason}"] += 1
                continue
            span_size = HEADER.size + chunk.stored_size
            owned = _owning_segment(entry, chunk.offset, span_size)
            if owned is None and info.name not in PLAYER_STRIP_NAMES:
                skipped[f"{info.name}: span crosses a pack boundary"] += 1
                continue
            if len(entry.segments) != 1 and info.name not in {
                "logo", "chiclet", "splayer", "flipchip",
            } | PLAYER_STRIP_NAMES:
                continue
            span = data[chunk.offset:chunk.offset + span_size]
            physical_spans = _physical_span_records(entry, chunk.offset, span)
            group, label = FAMILIES[info.name]
            record: dict[str, object] = {
                "asset_id": f"p8:{outer_index}:{info.name}",
                "chunk_index": position,
                "group": group,
                "height": info.height,
                "label": label,
                "mip_levels": info.mip_levels,
                "format_name": info.format_name,
                "outer_index": outer_index,
                "palette_offset": info.palette_offset,
                "pixel_chain_bytes": (
                    sum(
                        max(1, info.width >> level)
                        * max(1, info.height >> level)
                        * (2 if info.format_name == "A1R5G5B5" else 1)
                        for level in range(info.mip_levels)
                    )
                ),
                "span_sha256": digest(span),
                "span_size": span_size,
                "texture": info.name,
                "width": info.width,
            }
            if owned is None:
                first = physical_spans[0]
                record.update({
                    "pack_name": first["pack_name"],
                    "pack_relative_offset": first["pack_relative_offset"],
                    "physical_spans": physical_spans,
                    "replacement_supported": True,
                })
            else:
                segment, offset_in_segment = owned
                record.update({
                    "pack_name": segment.pack_name,
                    "pack_relative_offset": segment.pack_offset + offset_in_segment,
                    "replacement_supported": True,
                })
            if info.name in PRESENTATION_NAMES:
                require(entry.name_id in presentation_metadata,
                        f"uniform presentation outer {outer_index} has no team labels")
                record.update(presentation_metadata[entry.name_id])
            targets.append(record)
    targets.sort(key=lambda row: (row["group"], row["texture"], row["outer_index"]))
    require(targets, "no eligible standalone P8 targets were found")
    groups = Counter(str(row["group"]) for row in targets)
    # Per-pack identity. The composed build locates each pack in the user's own
    # image, derives the absolute offset from where it actually lands, and then
    # checks the pack's content hash -- which is the same on every legal dump
    # because a pack is one file. That is why these are safe to pin and the
    # container's size and hash are not.
    packs = _pack_records(
        index_path,
        targets,
    )
    return {
        "schema": SCHEMA,
        "source": {"index": index_path.name},
        "summary": {
            "target_count": len(targets),
            "editable_target_count": sum(
                row.get("replacement_supported", True) is True for row in targets
            ),
            "export_only_target_count": sum(
                row.get("replacement_supported", True) is False for row in targets
            ),
            "group_counts": dict(sorted(groups.items())),
            "distinct_textures": len({str(row["texture"]) for row in targets}),
            "skipped": dict(sorted(skipped.items())),
        },
        "packs": packs,
        "contract": {
            "formats": ["P8", "A1R5G5B5"],
            "requires": "compressed swizzled P8 with an index chain at the "
                        "video-buffer start and a 1024-byte palette after the "
                        "complete mip chain; or a reviewed explicit-size linear "
                        "A1R5G5B5 p001..p006/p011..p016 five-level player strip",
            "excludes": "Stadium Studio's SCNE-embedded textures, which are a "
                        "separate corpus edited in the Stadiums workspace",
            "team_presentation_boundary": "Uniform-package logo/chiclet/splayer/"
                        "flipchip are distinct from live helmet/jersey textures "
                        "and from Team Select card rasters; exact runtime screen "
                        "ownership remains only partially mapped",
        },
        "targets": targets,
    }


def augment_uniform_presentation(index_path: Path, report_path: Path) \
        -> dict[str, object]:
    """Upgrade the previous 3,024-row report with the 2,536 uniform UI rows.

    The complete scanner remains the canonical clean-room generator.  This
    bounded upgrade exists so release preparation does not re-decompress every
    unrelated SCNE/TXTR in a multi-gigabyte private archive merely to append
    four already enumerated chunks from each of the 634 uniform packages.
    Every appended row is still reparsed and hashed from the private source.
    """

    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read existing P8 report: {exc}") from exc
    old_groups = {
        "End Zone": 1_770,
        "Equipment": 5,
        "Field Surface": 225,
        "Goalpost Pads": 1_024,
    }
    summary = document.get("summary") or {}
    targets = document.get("targets") or []
    require(document.get("schema") == SCHEMA, "existing P8 report schema changed")
    # Re-running the bounded upgrade is a deterministic refresh, not a reason
    # to demand the caller restore an older generated file first.
    if (
        summary.get("target_count") == 5_560
        and isinstance(targets, list)
        and len(targets) == 5_560
    ):
        targets = [row for row in targets if row.get("texture") not in PRESENTATION_NAMES]
        summary = {
            "target_count": len(targets),
            "group_counts": dict(sorted(Counter(
                str(row["group"]) for row in targets
            ).items())),
            "skipped": summary.get("skipped") or {},
        }
    require(summary.get("target_count") == 3_024 and
            summary.get("group_counts") == old_groups and
            isinstance(targets, list) and len(targets) == 3_024,
            "existing P8 report is not the exact pre-presentation inventory")
    names = ("logo", "chiclet", "splayer", "flipchip")
    presentation_metadata = _uniform_presentation_metadata()
    require(not any(row.get("texture") in names for row in targets),
            "existing P8 report already contains uniform presentation rows")

    archive = parse_archive(index_path)
    appended: list[dict[str, object]] = []
    for outer_index in range(3613, 4247):
        entry = archive.entries[outer_index]
        data = read_entry_bytes(archive, entry)
        chunks = parse_chunks(data, allow_trailing=True)
        require(len(chunks) == 53,
                f"uniform outer {outer_index} no longer has 53 chunks")
        for position, expected_name in zip(range(49, 53), names):
            chunk = chunks[position]
            require(chunk.kind == "TXTR",
                    f"uniform outer {outer_index} chunk {position} is not TXTR")
            decoded, _info = decode_chunk(data, chunk)
            info = parse_texture(decoded, chunk)
            require(info.name == expected_name,
                    f"uniform outer {outer_index} chunk {position} changed name")
            reason = eligible(info, chunk)
            require(reason is None,
                    f"uniform outer {outer_index} {expected_name}: {reason}")
            span_size = HEADER.size + chunk.stored_size
            owned = _owning_segment(entry, chunk.offset, span_size)
            require(owned is not None,
                    f"uniform outer {outer_index} {expected_name} crosses a pack boundary")
            segment, offset_in_segment = owned
            span = data[chunk.offset:chunk.offset + span_size]
            group, label = FAMILIES[expected_name]
            record = {
                "asset_id": f"p8:{outer_index}:{expected_name}",
                "chunk_index": position,
                "group": group,
                "height": info.height,
                "label": label,
                "mip_levels": info.mip_levels,
                "outer_index": outer_index,
                "pack_name": segment.pack_name,
                "pack_relative_offset": segment.pack_offset + offset_in_segment,
                "palette_offset": info.palette_offset,
                "span_sha256": digest(span),
                "span_size": span_size,
                "texture": expected_name,
                "width": info.width,
            }
            require(entry.name_id in presentation_metadata,
                    f"uniform presentation outer {outer_index} has no team labels")
            record.update(presentation_metadata[entry.name_id])
            appended.append(record)
    require(len(appended) == 2_536,
            "uniform presentation target count changed")
    targets.extend(appended)
    targets.sort(key=lambda row: (
        str(row["group"]), str(row["texture"]), int(row["outer_index"])
    ))
    groups = Counter(str(row["group"]) for row in targets)
    document["targets"] = targets
    document["packs"] = {
        **(document.get("packs") or {}),
        **_pack_records(index_path, appended),
    }
    document["summary"] = {
        "target_count": len(targets),
        "group_counts": dict(sorted(groups.items())),
        "distinct_textures": len({str(row["texture"]) for row in targets}),
        "skipped": summary.get("skipped") or {},
    }
    contract = document.setdefault("contract", {})
    contract["team_presentation_boundary"] = (
        "Uniform-package logo/chiclet/splayer/flipchip are distinct from live "
        "helmet/jersey textures and from Team Select card rasters; exact "
        "runtime screen ownership remains only partially mapped"
    )
    return document


def augment_player_strips(index_path: Path, report_path: Path) \
        -> dict[str, object]:
    """Append the 4,080 proved A1 player strips to the current 5,560 rows.

    This bounded refresh touches only the 510 owning outer packages and keeps
    the existing P8 rows exact. It exists for release preparation; ``build``
    remains the canonical full clean-room generator.
    """

    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read existing texture report: {exc}") from exc
    summary = document.get("summary") or {}
    targets = document.get("targets") or []
    require(document.get("schema") == SCHEMA,
            "existing texture report schema changed")
    if summary.get("target_count") == 9_640:
        targets = [
            row for row in targets
            if str(row.get("texture")) not in PLAYER_STRIP_NAMES
        ]
    require(isinstance(targets, list) and len(targets) == 5_560,
            "existing texture report is not the exact pre-player-strip inventory")
    require(not any(
        str(row.get("texture")) in PLAYER_STRIP_NAMES for row in targets
    ), "existing texture report already contains player strips")

    archive = parse_archive(index_path)
    appended: list[dict[str, object]] = []
    for outer_index in range(513, 1_023):
        entry = archive.entries[outer_index]
        data = read_entry_bytes(archive, entry)
        for position, chunk in enumerate(parse_chunks(data, allow_trailing=True)):
            if chunk.kind != "TXTR":
                continue
            decoded, _info = decode_chunk(data, chunk)
            info = parse_texture(decoded, chunk)
            if info.name not in PLAYER_STRIP_NAMES:
                continue
            reason = eligible(info, chunk)
            require(reason is None,
                    f"outer {outer_index} {info.name}: {reason}")
            span_size = HEADER.size + chunk.stored_size
            owned = _owning_segment(entry, chunk.offset, span_size)
            chain = sum(
                max(1, info.width >> level)
                * max(1, info.height >> level) * 2
                for level in range(info.mip_levels)
            )
            span = data[chunk.offset:chunk.offset + span_size]
            physical_spans = _physical_span_records(entry, chunk.offset, span)
            group, label = FAMILIES[info.name]
            record: dict[str, object] = {
                "asset_id": f"p8:{outer_index}:{info.name}",
                "chunk_index": position,
                "format_name": info.format_name,
                "group": group,
                "height": info.height,
                "label": label,
                "mip_levels": info.mip_levels,
                "outer_index": outer_index,
                "palette_offset": info.palette_offset,
                "pixel_chain_bytes": chain,
                "span_sha256": digest(span),
                "span_size": span_size,
                "texture": info.name,
                "video_tail_bytes": chunk.video_bytes - chain,
                "width": info.width,
            }
            if owned is None:
                # Exactly one retail strip (outer 581 p005) straddles pack 0/1.
                # Record both source-owned pieces so the composed build can
                # stage and verify the exact logical chain transactionally.
                first = physical_spans[0]
                record.update({
                    "pack_name": first["pack_name"],
                    "pack_relative_offset": first["pack_relative_offset"],
                    "physical_spans": physical_spans,
                    "replacement_supported": True,
                })
            else:
                segment, offset_in_segment = owned
                record.update({
                    "pack_name": segment.pack_name,
                    "pack_relative_offset": segment.pack_offset + offset_in_segment,
                    "replacement_supported": True,
                })
            appended.append(record)
    require(len(appended) == 4_080,
            f"A1 player-strip target count changed: found {len(appended)}")
    require(Counter(str(row["texture"]) for row in appended)
            == Counter({name: 340 for name in PLAYER_STRIP_NAMES}),
            "A1 player-strip per-name counts changed")
    targets.extend(appended)
    targets.sort(key=lambda row: (
        str(row["group"]), str(row["texture"]), int(row["outer_index"])
    ))
    groups = Counter(str(row["group"]) for row in targets)
    document["targets"] = targets
    document["summary"] = {
        "target_count": len(targets),
        "editable_target_count": sum(
            row.get("replacement_supported", True) is True for row in targets
        ),
        "export_only_target_count": sum(
            row.get("replacement_supported", True) is False for row in targets
        ),
        "group_counts": dict(sorted(groups.items())),
        "distinct_textures": len({str(row["texture"]) for row in targets}),
        "skipped": summary.get("skipped") or {},
    }
    contract = document.setdefault("contract", {})
    contract.pop("format", None)
    contract["formats"] = ["P8", "A1R5G5B5"]
    contract["player_strip_boundary"] = (
        "Only p001..p006 and p011..p016 use the measured explicit-size "
        "five-level linear A1 layout; their source-owned video tails are "
        "preserved byte-for-byte and no other A1 texture is inferred editable."
    )
    return document


def augment_menu_presentation(index_path: Path, report_path: Path) \
        -> dict[str, object]:
    """Append every proved team-facing menu/presentation logo surface.

    This bounded pass adds three exact raw-P8 aggregate owners (``logos.cdf``,
    ``mini.cdf``, and ``flipchip.cdf``) plus only the logo-bearing chunks in
    the 85 ``frNN.iff`` franchise packages.  It intentionally excludes the
    neighboring office photos, crowd uniforms, inflatable helmets, stadium
    box logos, Crib team logos, and the two unnamed mini slots.
    """

    try:
        document = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read existing texture report: {exc}") from exc
    require(document.get("schema") == SCHEMA,
            "existing texture report schema changed")
    summary = document.get("summary") or {}
    targets = document.get("targets") or []
    require(isinstance(targets, list), "existing texture targets are not a list")
    if summary.get("target_count") == 11_395 and len(targets) == 11_395:
        targets = [
            row for row in targets
            if str(row.get("presentation_family") or "")
            not in MENU_PRESENTATION_FAMILIES
        ]
    require(len(targets) == 9_640,
            "existing texture report is not the exact pre-menu-closure inventory")
    require(not any(
        str(row.get("presentation_family") or "") in MENU_PRESENTATION_FAMILIES
        for row in targets
    ), "existing texture report already contains menu-closure rows")

    archive = parse_archive(index_path)
    logical_metadata, team_metadata = _team_style_metadata()
    appended: list[dict[str, object]] = []

    def append_target(
        *,
        entry: object,
        outer_index: int,
        position: int,
        chunk: object,
        data: bytes,
        info: object,
        metadata: dict[str, object],
        family: str,
        group: str,
        label: str,
        outer_name: str,
        consumer_scope: str,
        fixed_slot_padding: int | None = None,
        resource_offset: int | None = None,
    ) -> None:
        reason = eligible(info, chunk)
        require(reason is None, f"outer {outer_index} {info.name}: {reason}")
        span_size = HEADER.size + chunk.stored_size
        effective_offset = chunk.offset if resource_offset is None else resource_offset
        span = data[effective_offset:effective_offset + span_size]
        require(len(span) == span_size, f"outer {outer_index} {info.name} span is short")
        owned = _owning_segment(entry, effective_offset, span_size)
        require(owned is not None,
                f"outer {outer_index} {info.name} crosses a pack boundary")
        segment, offset_in_segment = owned
        record: dict[str, object] = {
            "asset_id": f"p8:{outer_index}:{info.name}",
            "chunk_index": position,
            "compressed": bool(chunk.compressed),
            "consumer_scope": consumer_scope,
            "format_name": info.format_name,
            "group": group,
            "height": info.height,
            "label": label,
            "mip_levels": info.mip_levels,
            "outer_index": outer_index,
            "outer_name": outer_name,
            "pack_name": segment.pack_name,
            "pack_relative_offset": segment.pack_offset + offset_in_segment,
            "palette_offset": info.palette_offset,
            "pixel_chain_bytes": info.palette_offset,
            "presentation_family": family,
            "replacement_supported": True,
            "span_sha256": digest(span),
            "span_size": span_size,
            "system_bytes": chunk.system_bytes,
            "texture": info.name,
            "video_bytes": chunk.video_bytes,
            "width": info.width,
            **metadata,
        }
        if fixed_slot_padding is not None:
            record.update({
                "post_span_padding_all_zero": True,
                "post_span_padding_bytes": fixed_slot_padding,
                "slot_size": span_size + fixed_slot_padding,
            })
        appended.append(record)

    aggregate_counts: Counter[str] = Counter()
    for outer_index, outer_spec in MENU_AGGREGATE_SPECS.items():
        entry = archive.entries[outer_index]
        expected_name = str(outer_spec["outer_name"])
        expected_id = zlib.crc32(
            expected_name.upper().encode("utf-16le")
        ) & 0xFFFFFFFF
        require(
            entry.name_id == expected_id == int(outer_spec["outer_id"])
            and entry.size == int(outer_spec["outer_size"])
            and len(entry.segments) == 1
            and entry.segments[0].pack_name == "3",
            f"{expected_name} outer identity changed",
        )
        data = read_entry_bytes(archive, entry)
        slot_size = int(outer_spec["width"]) * int(outer_spec["height"]) + 1_280
        span_size = slot_size - 96
        require(
            entry.size % slot_size == 0,
            f"{expected_name} is no longer a complete fixed-slot array",
        )
        for position in range(entry.size // slot_size):
            resource_offset = position * slot_size
            span = data[resource_offset:resource_offset + span_size]
            padding = data[resource_offset + span_size:resource_offset + slot_size]
            chunks = parse_chunks(span)
            require(
                len(chunks) == 1 and chunks[0].kind == "TXTR",
                f"{expected_name} slot {position} is not one raw TXTR",
            )
            chunk = chunks[0]
            decoded, decode_info = decode_chunk(span, chunk)
            info = parse_texture(decoded, chunk)
            variants = list(outer_spec.get("patterns") or (outer_spec,))
            matched_spec: dict[str, object] | None = None
            match: re.Match[str] | None = None
            for candidate in variants:
                candidate_match = candidate["pattern"].fullmatch(info.name)
                if candidate_match is not None:
                    matched_spec = candidate
                    match = candidate_match
                    break
            if matched_spec is None or match is None:
                continue
            width = int(outer_spec["width"])
            height = int(outer_spec["height"])
            require(
                decode_info is None
                and not chunk.compressed
                and chunk.compression_magic == 0
                and chunk.system_bytes == 128
                and chunk.video_bytes == width * height + 1_024
                and chunk.stored_size == chunk.system_bytes + chunk.video_bytes
                and info.format_name == "P8"
                and info.packed_size == 0
                and info.pixel_offset == 0
                and info.palette_offset == width * height
                and info.mip_levels == 1
                and (info.width, info.height, info.depth) == (width, height, 1),
                f"{expected_name} {info.name} left its raw fixed-slot P8 class",
            )
            require(
                padding == bytes(96),
                f"{expected_name} {info.name} fixed-slot padding changed",
            )
            code = match.group("code")
            style = int(match.group("style"))
            key = (code, style)
            require(key in logical_metadata,
                    f"{expected_name} {info.name} has no team/style owner")
            metadata = dict(logical_metadata[key])
            side = match.groupdict().get("side")
            if side is not None:
                side_code = side.upper()
                selector_index = 0 if side_code == "H" else 1
                metadata.update({
                    "set_selector": metadata["set_selectors"][selector_index],
                    "side_code": side_code,
                    "side_context": "home" if side_code == "H" else "away",
                })
            else:
                metadata["set_selector"] = " / ".join(metadata["set_selectors"])
            family = str(matched_spec["family"])
            append_target(
                entry=entry,
                outer_index=outer_index,
                position=position,
                chunk=chunk,
                data=data,
                info=info,
                metadata=metadata,
                family=family,
                group=str(matched_spec["group"]),
                label=str(matched_spec["label"]),
                outer_name=expected_name,
                consumer_scope={
                    "menu_logo_large": "Player pop-ups, simulator, SportsCenter wrapups, and Cap Manager",
                    "menu_logo_small": "FRMINI season, weekly-prep, transaction, and related compact menus",
                    "menu_flipchip": "Menu lineups, playoff picture, awards, and draft/presentation screens",
                    "menu_mini_card": "MINIHELMETS pending-trade and online user-card screens",
                }[family],
                fixed_slot_padding=96,
                resource_offset=resource_offset,
            )
            aggregate_counts[family] += 1

    require(
        aggregate_counts == Counter({
            "menu_logo_large": 317,
            "menu_logo_small": 317,
            "menu_flipchip": 317,
            "menu_mini_card": 634,
        }),
        f"aggregate menu target counts changed: {dict(aggregate_counts)}",
    )

    for ordinal, code in enumerate(FRANCHISE_ASSET_CODES):
        outer_index = 24 + ordinal
        entry = archive.entries[outer_index]
        outer_name = f"fr{code}.iff"
        require(
            entry.name_id
            == zlib.crc32(outer_name.upper().encode("utf-16le")) & 0xFFFFFFFF,
            f"{outer_name} outer identity changed",
        )
        data = read_entry_bytes(archive, entry)
        chunks = parse_chunks(data, allow_trailing=True)
        require(len(chunks) == 4, f"{outer_name} no longer has four resources")
        for excluded_position, excluded_name in (
            (2, "wallphoto"),
            (3, "office_photos"),
        ):
            excluded_chunk = chunks[excluded_position]
            require(
                excluded_chunk.kind == "TXTR",
                f"{outer_name} excluded chunk {excluded_position} changed type",
            )
            excluded_decoded, _excluded_decode = decode_chunk(
                data, excluded_chunk
            )
            excluded_info = parse_texture(excluded_decoded, excluded_chunk)
            require(
                excluded_info.name == excluded_name,
                f"{outer_name} excluded franchise art boundary changed",
            )
        require(code in team_metadata, f"{outer_name} has no team owner")
        base_metadata = dict(team_metadata[code])
        base_metadata.update({
            "set_selector": code,
            "style_display": "Team-wide franchise presentation",
        })
        for position, expected_texture, family, label, scope in (
            (
                0,
                f"{code}_teamlogo_00_h0",
                "franchise_team_logo",
                "Team Logo — Franchise Office",
                "FRANCHISE2 coach_desk teamlogo",
            ),
            (
                1,
                "pdalogo",
                "draft_pda_logo",
                "Team Logo — Draft PDA",
                "Franchise draft and PDA menu presentation",
            ),
        ):
            chunk = chunks[position]
            require(chunk.kind == "TXTR" and chunk.compressed,
                    f"{outer_name} {expected_texture} compression class changed")
            decoded, decode_info = decode_chunk(data, chunk)
            info = parse_texture(decoded, chunk)
            expected_dimensions = (256, 256) if position == 0 else (64, 64)
            require(
                decode_info is not None
                and info.name == expected_texture
                and info.format_name == "P8"
                and info.packed_size == 0
                and info.pixel_offset == 0
                and info.palette_offset == expected_dimensions[0] * expected_dimensions[1]
                and info.mip_levels == 1
                and (info.width, info.height) == expected_dimensions,
                f"{outer_name} {expected_texture} layout changed",
            )
            append_target(
                entry=entry,
                outer_index=outer_index,
                position=position,
                chunk=chunk,
                data=data,
                info=info,
                metadata=dict(base_metadata),
                family=family,
                group="Franchise & Draft Presentation",
                label=label,
                outer_name=outer_name,
                consumer_scope=scope,
            )

    require(len(appended) == 1_755,
            f"menu/presentation closure count changed: {len(appended)}")
    require(len({str(row["asset_id"]) for row in appended}) == len(appended),
            "menu/presentation closure repeats an asset ID")
    existing_ids = {str(row["asset_id"]) for row in targets}
    require(not existing_ids.intersection(str(row["asset_id"]) for row in appended),
            "menu/presentation closure overlaps an existing target")

    targets.extend(appended)
    targets.sort(key=lambda row: (
        str(row["group"]), str(row["texture"]), int(row["outer_index"])
    ))
    groups = Counter(str(row["group"]) for row in targets)
    document["targets"] = targets
    document["packs"] = {
        **(document.get("packs") or {}),
        **_pack_records(index_path, appended),
    }
    document["summary"] = {
        "target_count": len(targets),
        "editable_target_count": sum(
            row.get("replacement_supported", True) is True for row in targets
        ),
        "export_only_target_count": sum(
            row.get("replacement_supported", True) is False for row in targets
        ),
        "group_counts": dict(sorted(groups.items())),
        "distinct_textures": len({str(row["texture"]) for row in targets}),
        "skipped": summary.get("skipped") or {},
    }
    contract = document.setdefault("contract", {})
    contract["menu_presentation_boundary"] = (
        "All 1,585 named team-linked raw slots in logos.cdf, mini.cdf, and "
        "flipchip.cdf plus the 170 franchise-office/draft logo TXTRs are "
        "editable. The two unknown mini slots, wallphoto, office_photos, "
        "uniformlogo, inflatablehelmet, boxlogo, and Crib-owned team logos "
        "remain outside this family. Franchise teamlogo is not midfield art."
    )
    contract["raw_p8_fixed_slot"] = (
        "Raw menu atlases preserve the 32-byte wrapper, 128-byte system "
        "region, descriptor, exact 66,720/5,280-byte resource span, and "
        "source-owned 96-byte slot padding; only swizzled indices and the "
        "1,024-byte palette are regenerated. VC-LZ is not involved."
    )
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument(
        "--augment-uniform-presentation",
        action="store_true",
        help="upgrade the exact 3,024-row report by rescanning only uniform chunks 49..52",
    )
    parser.add_argument(
        "--augment-player-strips",
        action="store_true",
        help="upgrade the exact 5,560-row report by rescanning only A1 player strips",
    )
    parser.add_argument(
        "--augment-menu-presentation",
        action="store_true",
        help="upgrade the exact 9,640-row report with all proved menu/presentation logo surfaces",
    )
    args = parser.parse_args()
    try:
        index = args.index.resolve(strict=True)
        require(sum((
            args.augment_uniform_presentation,
            args.augment_player_strips,
            args.augment_menu_presentation,
        )) <= 1, "choose only one bounded augmentation mode")
        if args.augment_uniform_presentation:
            document = augment_uniform_presentation(index, args.json)
        elif args.augment_player_strips:
            document = augment_player_strips(index, args.json)
        elif args.augment_menu_presentation:
            document = augment_menu_presentation(index, args.json)
        else:
            document = build(index)
    except InventoryError as exc:
        print(f"nfl_p8_texture_inventory: {exc}", file=sys.stderr)
        return 2
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    summary = document["summary"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
