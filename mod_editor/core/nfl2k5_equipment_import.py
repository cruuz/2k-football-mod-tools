"""Preflight the complete equipment TSET before one undoable Studio import.

Which package copy the game samples decides where an import has to go
(``nfl2k5_uniform_equipment_writer.consumer_targets``).  Team-coloured
variants are package-local.  Generic variants -- Style 1/2/4/5 shoes, gloves
1-4, elbow pads 1-4, long sleeves 1-2, wristbands 1-2 -- are one league-wide
texture at runtime: the executable binds the copy inside the most recently
loaded uniform package (the away team's package in a game, the viewed team's
``h0``/``a0`` package on the Edit Player screen).  Staging one package only
ever reached the Edit Player preview, so a generic variant is staged, as one
undoable transaction, into every package the game can sample it from.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import tempfile
from typing import Any

from .errors import ValidationError
from .nfl2k5_equipment_import_intent import (
    retail_source, same_visual_import, with_import_mode, with_retail_source,
)


CONSUMER_SCHEMA = "nfl2k5_equipment_consumer_fanout/v1"
GLOBAL_RULE = (
    "All teams share this style because the game reads its texture from the most recently loaded uniform package."
)
CONTEXT_FIRST_RULE = "The game reads this variant from each team's own uniform package."
PACKAGE_LOCAL_SHOE_HELP = (
    "For team-specific shoe artwork, import shoes09 (Style 3) or shoes10 (Style 6) "
    "in each uniform package you use, and select that style for each player's left and right shoe."
)
ALL_TEAMS = "all-teams"
SELECTED_PACKAGE = "selected-package"


def equipment_import_scope(asset_id: str) -> tuple[tuple[tuple[str, str], ...], str]:
    """The dialog and non-GUI callers use the same reviewed scope contract."""
    from .nfl2k5_uniform_equipment_writer import in_game_lookup, load_targets

    target = load_targets()[0].get(asset_id)
    if target is None:
        raise ValidationError("Choose a reviewed equipment texture.")
    if in_game_lookup(target.name) == "global":
        return ((ALL_TEAMS, "All teams"),), GLOBAL_RULE
    return ((SELECTED_PACKAGE, "Selected uniform package"),), CONTEXT_FIRST_RULE


@dataclass(frozen=True)
class EquipmentImportResult:
    message: str
    receipt: dict[str, Any]
    changed_asset_ids: tuple[str, ...]
    modified: bool
    consumer_asset_ids: tuple[str, ...] = ()


def _package_counts(consumers: Any) -> dict[str, int]:
    away = sum(1 for item in consumers if item.set_selector[2:3] == "A")
    home_current = sum(1 for item in consumers if item.set_selector[2:] == "H0")
    return {"away": away, "home_current": home_current,
            "selected_only": len(consumers) - away - home_current}


def _consumer_receipt(target: Any, consumers: Any, staged: tuple[str, ...]) -> dict[str, Any]:
    from .nfl2k5_uniform_equipment_writer import BINDING_TABLE_ROWS, in_game_lookup

    lookup = in_game_lookup(target.name)
    base = target.name[:-4] if target.name.endswith("_mud") else target.name
    return {
        "schema": CONSUMER_SCHEMA,
        "selected_asset_id": target.asset_id,
        "name": target.name,
        "in_game_lookup": lookup,
        "rule": GLOBAL_RULE if lookup == "global" else CONTEXT_FIRST_RULE,
        "xbe_evidence": {
            "binding_table": "0x004EEAF8",
            "row": BINDING_TABLE_ROWS[base],
            "context_first": int(lookup == "context_first"),
            "lookup": ("FUN_0008E580 -> FUN_000449E0(0, 'TXTR', name): newest loaded context wins"
                       if lookup == "global" else
                       "FUN_0008E580 -> FUN_000449E0(HOME/AWAY, 'TXTR', name)"),
            "game_load_order": "FUN_00062BE0 creates HOME at 0x0006327A, then AWAY at 0x00063298",
            "front_end_preview": "FUN_00091940 loads <code>h0.iff or <code>a0.iff alone",
        },
        "package_counts": _package_counts(consumers),
        "consumer_asset_ids": [item.asset_id for item in consumers],
        "staged_asset_ids": list(staged),
    }


def _message(target: Any, consumers: Any, *, independent: bool,
             encoded: str, approximation: str, changed: bool) -> str:
    from .nfl2k5_uniform_equipment_writer import in_game_lookup

    count = len(consumers)
    if in_game_lookup(target.name) == "global":
        counts = _package_counts(consumers)
        where = (
            f"{count} uniform packages ({counts['away']} away, {counts['home_current']} home Current Uniform"
            + (f", {counts['selected_only']} selected only" if counts["selected_only"] else "") + ")"
        )
        scope = (f"In a game every player wearing this style uses the away team's package copy, "
                 f"so it was staged into all {where}.")
    else:
        scope = "This variant is read from each team's own package, so only this package changed."
    if not changed:
        return "Equipment artwork and its import choice already match the project."
    if independent:
        return (f"Equipment artwork is ready to build at {encoded}.{approximation} "
                f"Experimental / unwitnessed. {scope}")
    return f"Equipment recolour is ready to build.{approximation} {scope}"


def stage_equipment_import(session: Any, asset: Any, path: Path, *,
                           independent: bool | None = None, scale: int = 1,
                           scope: str | None = None) -> EquipmentImportResult:
    from .nfl2k5_uniform_equipment_writer import (
        build_unified_uniform_equipment_imports, consumer_targets, encode_rgba_png, load_targets,
    )

    by_id, _groups = load_targets()
    target = by_id.get(asset.asset_id)
    if target is None or getattr(asset, "kind", None) != "uniform_equipment_texture":
        raise ValidationError("Choose a reviewed equipment texture.")
    choices, rule = equipment_import_scope(asset.asset_id)
    if scope is not None and scope not in {value for value, _label in choices}:
        raise ValidationError(rule)
    payload, rgba = session.asset_io.validate_replacement(asset, path)
    original, original_rgba = session.asset_io.validate_replacement(
        asset, session.asset_io.ensure_original(asset),
    )
    if independent is None:
        from .nfl2k5_equipment_import_intent import supports_own_texture
        independent = supports_own_texture(asset.asset_id) and rgba != original_rgba
    frozen = with_import_mode(payload, asset.asset_id, rgba, independent=independent, scale=scale)
    restoring = same_visual_import(asset, frozen, rgba, original, original_rgba)
    consumers = consumer_targets(target, by_id)
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
        # Every other package the game can sample this variant from receives
        # the same decoded pixels: a canonical PNG (never the user's possibly
        # large file) carrying its own explicit texture choice. Restoring the
        # original restores every copy that is currently staged.
        rows: list[tuple[Any, Path]] = []
        canonical = with_retail_source(encode_rgba_png(target.width, target.height, rgba),
                                       retail_source(frozen, rgba), rgba)
        for copy in consumers:
            if copy.asset_id == asset.asset_id:
                rows.append((asset, staged))
                continue
            copy_asset = session._visual_asset(copy.asset_id)
            if restoring:
                if session.is_modified(copy.asset_id):
                    rows.append((copy_asset, session.asset_io.ensure_original(copy_asset)))
                continue
            copy_png = Path(directory).resolve() / f"{copy.outer_index}_{copy.chunk_index}_{copy.reference_index}.png"
            copy_png.write_bytes(with_import_mode(
                canonical, copy.asset_id, rgba, independent=independent, scale=scale,
            ))
            rows.append((copy_asset, copy_png))
        result = session.replace_batch(tuple(rows), label="Import equipment texture")
    staged_ids = tuple(row_asset.asset_id for row_asset, _row_path in rows)
    consumer_ids = tuple(item.asset_id for item in consumers)
    receipt = dict(receipt)
    receipt["consumers"] = _consumer_receipt(target, consumers, () if restoring else staged_ids)
    if restoring:
        return EquipmentImportResult(
            f"Equipment artwork was restored to the original in {len(rows)} package"
            f"{'s' if len(rows) != 1 else ''}.",
            receipt, result.changed_asset_ids, False, consumer_ids,
        )
    selected = next(row for row in receipt["edits"] if row["asset_id"] == asset.asset_id)
    encoded = " x ".join(str(value) for value in selected["encoded_dimensions"])
    quality = selected["palette_quality"] or {}
    from .equipment_palette import merge_message
    approximation = merge_message(quality)
    if selected["size_reduction"] != 1:
        approximation += (f" Detail was reduced from {target.width} x {target.height} to {encoded} "
                          "because a smaller game image was selected.")
    if selected["mip_filter"] == "preserved_retail_chain":
        approximation += " The unchanged retail palette and all distance images were preserved exactly."
    elif independent:
        approximation += " Distance images were regenerated from the imported base image."
    return EquipmentImportResult(
        _message(target, consumers, independent=independent, encoded=encoded,
                 approximation=approximation, changed=bool(result.changed_asset_ids)),
        receipt, result.changed_asset_ids, asset.asset_id in result.modified_asset_ids, consumer_ids,
    )


def revert_equipment_import(session: Any, asset: Any) -> tuple[str, ...]:
    """Revert every staged copy the game samples for ``asset``'s variant.

    Returns the asset IDs whose staged replacement was removed, as one
    undoable transaction; an empty tuple when nothing was staged.
    """

    from .nfl2k5_uniform_equipment_writer import consumer_targets, load_targets

    by_id, _groups = load_targets()
    target = by_id.get(getattr(asset, "asset_id", None))
    if target is None or getattr(asset, "kind", None) != "uniform_equipment_texture":
        raise ValidationError("Choose a reviewed equipment texture.")
    rows: list[tuple[Any, Path]] = []
    for copy in consumer_targets(target, by_id):
        if not session.is_modified(copy.asset_id):
            continue
        copy_asset = asset if copy.asset_id == asset.asset_id else session._visual_asset(copy.asset_id)
        rows.append((copy_asset, session.asset_io.ensure_original(copy_asset)))
    if not rows:
        return ()
    result = session.replace_batch(tuple(rows), label=f"Revert {asset.label}")
    return result.changed_asset_ids
