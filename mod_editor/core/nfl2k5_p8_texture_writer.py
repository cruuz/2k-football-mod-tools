"""Compose one reviewed standalone texture replacement into the unified build.

This is the piece that was missing when "All Textures" shipped as a sidebar
entry with nothing behind it.  The writer existed and was proved on three
differently packed dumps; what it had no route into was **Build Modded XISO**,
so an edit made in a browser would have been dropped on the way to the disc.
A workspace whose edits silently vanish at build time is worse than no
workspace, which is why this landed before any page did.

The corpus is the standalone ``TXTR`` chunks catalogued by
``tools/nfl_p8_texture_inventory.py``: the explicit-size A1 player strips, the
real teams' end-zone panels, stadium goalpost pads, grass overlays, shared
equipment, four per-uniform presentation textures, the separate raw menu-logo
atlases, mini cards, and franchise/draft logos. It deliberately does not
overlap Stadium Studio, SCNE-embedded textures, Crib-owned team logos, or the
separately owned large Team Select card rasters.

Identity is per-extent throughout.  Each target names the pack that owns it,
and the composed build locates that pack in the user's own image, derives the
absolute offset from where it actually landed, and verifies the pack's content
hash and the retail span hash before writing anything.  Nothing here depends on
the container's size or hash, or on a pack sitting at any particular sector.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import nfl_all_texture_xiso_workflow as writer  # noqa: E402
from nfl_outer import parse_archive  # noqa: E402


SCHEMA = "nfl2k5_p8_texture_inventory/v1"
DEFAULT_REPORT = _ROOT / "reports/assets/nfl2k5_p8_texture_inventory.json"
MAX_REPORT_BYTES = 8 * 1024 * 1024
EXPECTED_TARGETS = 11_395
EXPECTED_EDITABLE_TARGETS = 11_395
EXPECTED_GROUPS = {
    "End Zone": 1_770,
    "Equipment": 5,
    "Field Surface": 225,
    "Franchise & Draft Presentation": 170,
    "Goalpost Pads": 1_024,
    "Player Presentation Strips": 4_080,
    "Team Logos — Menus / Presentation": 951,
    "Team Mini Cards — Menus / Presentation": 634,
    "Team Presentation — Menu / UI": 2_536,
}


class P8TextureWriterError(ValueError):
    """Raised when a target, report, or replacement fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise P8TextureWriterError(message)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class P8PhysicalSpan:
    pack_name: str
    pack_path: str
    pack_size: int
    pack_sha256: str
    pack_retail_sector: int
    pack_relative_offset: int
    replacement_offset: int
    size: int
    span_sha256: str


@dataclass(frozen=True)
class P8Target:
    asset_id: str
    label: str
    group: str
    texture: str
    outer_index: int
    chunk_index: int
    pack_name: str
    pack_path: str
    pack_size: int
    pack_sha256: str
    pack_retail_sector: int
    pack_relative_offset: int
    span_size: int
    span_sha256: str
    width: int
    height: int
    mip_levels: int
    format_name: str
    pixel_chain_bytes: int
    replacement_supported: bool
    refusal_reason: str
    physical_spans: tuple[P8PhysicalSpan, ...]

    @property
    def selector(self) -> str:
        return self.asset_id


def load_inventory(path: Path = DEFAULT_REPORT) -> dict[str, P8Target]:
    """Read the pinned target report, fail-closed on any drift."""
    resolved = path.expanduser()
    _require(resolved.is_file(), f"P8 texture inventory is missing: {path}")
    _require(resolved.stat().st_size <= MAX_REPORT_BYTES,
             "P8 texture inventory is unreasonably large")
    document = json.loads(resolved.read_text(encoding="utf-8"))
    _require(document.get("schema") == SCHEMA,
             f"P8 texture inventory schema must be {SCHEMA}")
    summary = document.get("summary") or {}
    _require(summary.get("target_count") == EXPECTED_TARGETS,
             "P8 texture inventory target count changed")
    _require(summary.get("group_counts") == EXPECTED_GROUPS,
             "P8 texture inventory group counts changed")
    _require(
        summary.get("editable_target_count") == EXPECTED_EDITABLE_TARGETS
        and summary.get("export_only_target_count") == 0,
        "P8 texture inventory editable/export-only counts changed",
    )
    _require(not summary.get("skipped"),
             "P8 texture inventory reports skipped targets")
    packs = document.get("packs") or {}
    _require(packs, "P8 texture inventory carries no pack identity")
    targets: dict[str, P8Target] = {}
    for row in document.get("targets") or ():
        replacement_supported = row.get("replacement_supported", True) is True
        raw_spans = row.get("physical_spans")
        if raw_spans is None:
            raw_spans = [{
                "pack_name": row["pack_name"],
                "pack_relative_offset": row["pack_relative_offset"],
                "replacement_offset": 0,
                "size": row["span_size"],
                "span_sha256": row["span_sha256"],
            }]
        _require(
            isinstance(raw_spans, list) and 1 <= len(raw_spans) <= 2,
            f"physical spans for {row['asset_id']} changed",
        )
        physical_spans: list[P8PhysicalSpan] = []
        for raw_piece in raw_spans:
            _require(isinstance(raw_piece, dict),
                     f"physical span for {row['asset_id']} is invalid")
            piece_pack = packs.get(str(raw_piece["pack_name"]))
            _require(piece_pack is not None,
                     f"pack {raw_piece['pack_name']} is not described")
            physical_spans.append(P8PhysicalSpan(
                pack_name=str(raw_piece["pack_name"]),
                pack_path=str(piece_pack["path"]),
                pack_size=int(piece_pack["size"]),
                pack_sha256=str(piece_pack["sha256"]),
                pack_retail_sector=int(piece_pack["retail_sector"]),
                pack_relative_offset=int(raw_piece["pack_relative_offset"]),
                replacement_offset=int(raw_piece["replacement_offset"]),
                size=int(raw_piece["size"]),
                span_sha256=str(raw_piece["span_sha256"]),
            ))
        _require(
            [piece.replacement_offset for piece in physical_spans]
            == [sum(prior.size for prior in physical_spans[:index])
                for index in range(len(physical_spans))]
            and sum(piece.size for piece in physical_spans) == int(row["span_size"]),
            f"physical span chain for {row['asset_id']} is incomplete",
        )
        pack = packs.get(str(row["pack_name"]))
        _require(pack is not None, f"pack {row['pack_name']} is not described")
        target = P8Target(
            asset_id=str(row["asset_id"]),
            label=str(row["label"]),
            group=str(row["group"]),
            texture=str(row["texture"]),
            outer_index=int(row["outer_index"]),
            chunk_index=int(row["chunk_index"]),
            pack_name=str(row["pack_name"]),
            pack_path=str(pack["path"]),
            pack_size=int(pack["size"]),
            pack_sha256=str(pack["sha256"]),
            pack_retail_sector=int(pack["retail_sector"]),
            pack_relative_offset=int(row["pack_relative_offset"]),
            span_size=int(row["span_size"]),
            span_sha256=str(row["span_sha256"]),
            width=int(row["width"]),
            height=int(row["height"]),
            mip_levels=int(row["mip_levels"]),
            format_name=str(row.get("format_name") or "P8"),
            pixel_chain_bytes=int(
                row.get("pixel_chain_bytes") or row.get("palette_offset") or 0
            ),
            replacement_supported=replacement_supported,
            refusal_reason=str(row.get("refusal_reason") or ""),
            physical_spans=tuple(physical_spans),
        )
        _require(target.asset_id not in targets,
                 f"P8 texture inventory repeats {target.asset_id}")
        targets[target.asset_id] = target
    _require(len(targets) == EXPECTED_TARGETS,
             "P8 texture inventory row count disagrees with its summary")
    _require(
        sum(target.replacement_supported for target in targets.values())
        == EXPECTED_EDITABLE_TARGETS,
        "P8 texture inventory editable row count disagrees with its summary",
    )
    return targets


def target_record(
    target: P8Target,
    physical_span: P8PhysicalSpan | None = None,
    physical_span_index: int = 0,
) -> dict[str, Any]:
    """The proof record the composed build binds against."""

    piece = physical_span or target.physical_spans[0]
    piece_count = len(target.physical_spans)
    selector = (
        target.asset_id
        if piece_count == 1
        else f"{target.asset_id}.physical{physical_span_index}"
    )
    return {
        "asset_id": target.asset_id,
        "chunk_index": target.chunk_index,
        "format": target.format_name,
        "height": target.height,
        "mip_levels": target.mip_levels,
        "outer_index": target.outer_index,
        "pack_offset": piece.pack_relative_offset,
        "selector": selector,
        "span_sha256": piece.span_sha256,
        "span_size": piece.size,
        "texture": target.texture,
        "width": target.width,
        "logical_span_sha256": target.span_sha256,
        "logical_span_size": target.span_size,
        "physical_span_count": piece_count,
        "physical_span_index": physical_span_index,
        "replacement_offset": piece.replacement_offset,
        # Recorded for the build proof. The absolute offset is re-derived from
        # wherever this pack actually lands in the user's image, and the sector
        # is never compared -- both describe how one disc was packed.
        "xiso_absolute_span_offset": (
            piece.pack_retail_sector * 2048 + piece.pack_relative_offset
        ),
        "xiso_pack_path": piece.pack_path,
        "xiso_pack_sector": piece.pack_retail_sector,
        "xiso_pack_sha256": piece.pack_sha256,
        "xiso_pack_size": piece.pack_size,
    }


def build_unified_p8_texture_imports(
    index: Path,
    asset_id: str,
    png: Path,
    inventory_path: Path = DEFAULT_REPORT,
) -> list[tuple[
    bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]
]]:
    """Return one or two staged physical edits for one logical TXTR import."""
    targets = load_inventory(inventory_path)
    target = targets.get(str(asset_id))
    _require(target is not None,
             f"{asset_id} is not a reviewed standalone texture")
    assert target is not None
    _require(
        target.replacement_supported,
        target.refusal_reason
        or f"{asset_id} is visible/exportable but has no proved write route",
    )
    archive = parse_archive(Path(index))
    try:
        resolved = writer.resolve_target(archive, target.outer_index, target.texture)
    except writer.TextureWorkflowError as exc:
        raise P8TextureWriterError(str(exc)) from exc
    _require(resolved.span_sha256 == target.span_sha256,
             f"retail span for {asset_id} differs from the pinned inventory")
    _require(
        len(resolved.physical_spans) == len(target.physical_spans)
        and all(
            (
                actual.pack_name,
                actual.pack_relative_offset,
                actual.replacement_offset,
                actual.size,
                actual.span_sha256,
            ) == (
                expected.pack_name,
                expected.pack_relative_offset,
                expected.replacement_offset,
                expected.size,
                expected.span_sha256,
            )
            for actual, expected in zip(
                resolved.physical_spans, target.physical_spans
            )
        ),
        f"physical span chain for {asset_id} moved",
    )
    _require((resolved.width, resolved.height) == (target.width, target.height),
             f"retail dimensions for {asset_id} changed")
    _require(
        resolved.format_name == target.format_name
        and resolved.pixel_chain_bytes == target.pixel_chain_bytes,
        f"retail texture layout for {asset_id} changed",
    )
    try:
        replacement, report = writer.build_replacement(resolved, Path(png))
    except (writer.TextureWorkflowError, ValueError) as exc:
        raise P8TextureWriterError(str(exc)) from exc
    _require(len(replacement) == target.span_size,
             "rebuilt span size differs from the retail span")
    _require(replacement != resolved.template_span,
             f"replacement equals retail for {asset_id}")
    results = []
    for part_index, piece in enumerate(target.physical_spans):
        replacement_piece = replacement[
            piece.replacement_offset:piece.replacement_offset + piece.size
        ]
        _require(len(replacement_piece) == piece.size,
                 "rebuilt physical span size differs from retail")
        proof = target_record(target, piece, part_index)
        proof["logical_replacement_sha256"] = _digest(replacement)
        record = {
            "schema": "nfl2k5_p8_texture_import/v1",
            "asset_id": target.asset_id,
            "label": target.label,
            "group": target.group,
            "logical_replacement_sha256": _digest(replacement),
            "replacement_sha256": _digest(replacement_piece),
            "target": proof,
            **{
                key: value for key, value in report.items()
                if key != "rebuilt_span_sha256"
            },
        }
        results.append((replacement_piece, [], record, str(proof["selector"]), proof))
    _require(
        b"".join(item[0] for item in results) == replacement,
        "staged physical spans do not reassemble to the rebuilt TXTR",
    )
    return results


def build_unified_p8_texture_import(
    index: Path,
    asset_id: str,
    png: Path,
    inventory_path: Path = DEFAULT_REPORT,
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Backward-compatible single-span adapter; use the plural form for builds."""

    results = build_unified_p8_texture_imports(
        index, asset_id, png, inventory_path
    )
    _require(
        len(results) == 1,
        f"{asset_id} crosses packs and requires the plural composed-build adapter",
    )
    return results[0]


__all__ = [
    "DEFAULT_REPORT",
    "EXPECTED_TARGETS",
    "P8Target",
    "P8TextureWriterError",
    "build_unified_p8_texture_import",
    "build_unified_p8_texture_imports",
    "load_inventory",
    "target_record",
]
