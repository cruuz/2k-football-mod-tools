"""Preflight the complete equipment TSET before one undoable Studio import."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import tempfile
from typing import Any

from .errors import ValidationError
from .nfl2k5_equipment_import_intent import same_visual_import, with_import_mode


@dataclass(frozen=True)
class EquipmentImportResult:
    message: str
    receipt: dict[str, Any]
    changed_asset_ids: tuple[str, ...]
    modified: bool


def stage_equipment_import(session: Any, asset: Any, path: Path, *,
                           independent: bool = False, scale: int = 1) -> EquipmentImportResult:
    from .nfl2k5_uniform_equipment_writer import (
        build_unified_uniform_equipment_imports, load_targets,
    )

    by_id, _groups = load_targets()
    target = by_id.get(asset.asset_id)
    if target is None or getattr(asset, "kind", None) != "uniform_equipment_texture":
        raise ValidationError("Choose a reviewed equipment texture.")
    payload, rgba = session.asset_io.validate_replacement(asset, path)
    frozen = with_import_mode(payload, asset.asset_id, rgba, independent=independent, scale=scale)
    original, original_rgba = session.asset_io.validate_replacement(
        asset, session.asset_io.ensure_original(asset),
    )
    restoring = same_visual_import(asset, frozen, rgba, original, original_rgba)
    # Preflight every staged sibling together. Separate palette/chain edits in
    # one TSET must share one compression budget and one physical build edit.
    current = []
    for edit in session.iter_edits():
        sibling = by_id.get(edit.asset_id)
        if (sibling is None or sibling.asset_id == asset.asset_id
                or (sibling.outer_index, sibling.chunk_index)
                != (target.outer_index, target.chunk_index)):
            continue
        if not 0 < edit.replacement_path.stat().st_size <= 32 * 1024 * 1024:
            raise ValidationError("A staged equipment PNG exceeds the import size bound.")
        if hashlib.sha256(edit.replacement_path.read_bytes()).hexdigest() != edit.replacement_sha256:
            raise ValidationError("A staged equipment PNG changed outside Mod Studio.")
        current.append((edit.asset_id, edit.replacement_path))
    with tempfile.TemporaryDirectory(prefix="equipment-import-", dir=session.replacements) as directory:
        staged = Path(directory).resolve() / "artwork.png"
        staged.write_bytes(frozen)
        requested = sorted(current if restoring else [*current, (asset.asset_id, staged)])
        if requested:
            _span, _previews, receipt, _selector, _target = build_unified_uniform_equipment_imports(
                session.cache.pack0, requested,
            )
        else:
            receipt = {"schema": "nfl2k5_equipment_import_restore/v1", "asset_id": asset.asset_id,
                       "source_pixels_restored": True}
        result = session.replace_batch(((asset, staged),), label="Import equipment texture")
    if restoring:
        return EquipmentImportResult("Equipment artwork was restored to the original.", receipt,
                                     result.changed_asset_ids, False)
    selected = next(row for row in receipt["edits"] if row["asset_id"] == asset.asset_id)
    encoded = " x ".join(str(value) for value in selected["encoded_dimensions"])
    quality = selected["palette_quality"] or {}
    approximation = (" Some colours were approximated." if quality.get("maximum_channel_error", 0) else "")
    return EquipmentImportResult(
        ("Equipment artwork and its import choice already match the project."
         if not result.changed_asset_ids else
         f"Equipment artwork is ready to build at {encoded}." + approximation + " Experimental / unwitnessed."
         if independent else "Equipment recolour is ready to build."),
        receipt, result.changed_asset_ids, asset.asset_id in result.modified_asset_ids,
    )
