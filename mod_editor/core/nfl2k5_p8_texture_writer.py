"""Compose one standalone P8 texture replacement into the unified build.

This is the piece that was missing when "All Textures" shipped as a sidebar
entry with nothing behind it.  The writer existed and was proved on three
differently packed dumps; what it had no route into was **Build Modded XISO**,
so an edit made in a browser would have been dropped on the way to the disc.
A workspace whose edits silently vanish at build time is worse than no
workspace, which is why this landed before any page did.

The corpus is the standalone ``TXTR`` chunks catalogued by
``tools/nfl_p8_texture_inventory.py``: the real teams' end-zone panels, the
stadium goalpost pads, the grass ``divots`` overlay, and the shared equipment
textures.  It deliberately does not overlap Stadium Studio, which edits
textures *embedded inside* SCNE scenes.

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
EXPECTED_TARGETS = 3_024
EXPECTED_GROUPS = {
    "End Zone": 1_770,
    "Equipment": 5,
    "Field Surface": 225,
    "Goalpost Pads": 1_024,
}


class P8TextureWriterError(ValueError):
    """Raised when a target, report, or replacement fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise P8TextureWriterError(message)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    _require(not summary.get("skipped"),
             "P8 texture inventory reports skipped targets")
    packs = document.get("packs") or {}
    _require(packs, "P8 texture inventory carries no pack identity")
    targets: dict[str, P8Target] = {}
    for row in document.get("targets") or ():
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
        )
        _require(target.asset_id not in targets,
                 f"P8 texture inventory repeats {target.asset_id}")
        targets[target.asset_id] = target
    _require(len(targets) == EXPECTED_TARGETS,
             "P8 texture inventory row count disagrees with its summary")
    return targets


def target_record(target: P8Target) -> dict[str, Any]:
    """The proof record the composed build binds against."""
    return {
        "asset_id": target.asset_id,
        "chunk_index": target.chunk_index,
        "format": "P8",
        "height": target.height,
        "mip_levels": target.mip_levels,
        "outer_index": target.outer_index,
        "pack_offset": target.pack_relative_offset,
        "selector": target.selector,
        "span_sha256": target.span_sha256,
        "span_size": target.span_size,
        "texture": target.texture,
        "width": target.width,
        # Recorded for the build proof. The absolute offset is re-derived from
        # wherever this pack actually lands in the user's image, and the sector
        # is never compared -- both describe how one disc was packed.
        "xiso_absolute_span_offset": (
            target.pack_retail_sector * 2048 + target.pack_relative_offset
        ),
        "xiso_pack_path": target.pack_path,
        "xiso_pack_sector": target.pack_retail_sector,
        "xiso_pack_sha256": target.pack_sha256,
        "xiso_pack_size": target.pack_size,
    }


def build_unified_p8_texture_import(
    index: Path,
    asset_id: str,
    png: Path,
    inventory_path: Path = DEFAULT_REPORT,
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Return one composed edit: replacement span, previews, report, selector."""
    targets = load_inventory(inventory_path)
    target = targets.get(str(asset_id))
    _require(target is not None,
             f"{asset_id} is not a replaceable standalone P8 texture")
    assert target is not None
    archive = parse_archive(Path(index))
    try:
        resolved = writer.resolve_target(archive, target.outer_index, target.texture)
    except writer.TextureWorkflowError as exc:
        raise P8TextureWriterError(str(exc)) from exc
    _require(resolved.span_sha256 == target.span_sha256,
             f"retail span for {asset_id} differs from the pinned inventory")
    _require(resolved.pack_relative_offset == target.pack_relative_offset,
             f"pack-relative offset for {asset_id} moved")
    _require((resolved.width, resolved.height) == (target.width, target.height),
             f"retail dimensions for {asset_id} changed")
    try:
        replacement, report = writer.build_replacement(resolved, Path(png))
    except (writer.TextureWorkflowError, ValueError) as exc:
        raise P8TextureWriterError(str(exc)) from exc
    _require(len(replacement) == target.span_size,
             "rebuilt span size differs from the retail span")
    _require(replacement != resolved.template_span,
             f"replacement equals retail for {asset_id}")
    previews: list[tuple[str, bytes]] = []
    record = {
        "schema": "nfl2k5_p8_texture_import/v1",
        "asset_id": target.asset_id,
        "label": target.label,
        "group": target.group,
        "replacement_sha256": _digest(replacement),
        "target": target_record(target),
        **{key: value for key, value in report.items() if key != "rebuilt_span_sha256"},
    }
    return replacement, previews, record, target.selector, target_record(target)


__all__ = [
    "DEFAULT_REPORT",
    "EXPECTED_TARGETS",
    "P8Target",
    "P8TextureWriterError",
    "build_unified_p8_texture_import",
    "load_inventory",
    "target_record",
]
