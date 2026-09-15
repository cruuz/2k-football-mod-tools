"""Atomic equipment staging, including a normal variant's dirty sibling.

The UI enters here. Consumer resolution and legacy import contracts stay in
their existing modules; one combined compile supplies the actual fit receipt.
"""
from collections import defaultdict
from pathlib import Path
import hashlib
import tempfile

from .errors import ValidationError
from .nfl2k5_equipment_import import EquipmentImportResult, equipment_import_scope, _consumer_receipt
from .nfl2k5_equipment_import_intent import (
    supports_own_texture, with_import_mode, same_visual_import, retail_source, with_retail_source,
)


def staging_targets(target, by_id):
    """Normal imports include mud where that catalog sibling actually exists.

    An explicit mud import remains independent. Gloves without a mud descriptor
    keep their single slot; no speculative variant or package is invented.
    """
    from .nfl2k5_uniform_equipment_writer import consumer_targets
    rows = {t.asset_id: t for t in consumer_targets(target, by_id)}
    if not target.name.endswith("_mud") and target.name.startswith(("shoes", "glove", "elbowpad")):
        for sibling in by_id.values():
            if (sibling.outer_index == target.outer_index
                    and sibling.name == target.name + "_mud"):
                rows.update((t.asset_id, t) for t in consumer_targets(sibling, by_id))
    return tuple(sorted(rows.values(), key=lambda t: (t.outer_index, t.chunk_index, t.reference_index)))


def _checked_rows(session, paths, by_id, *, selected=None):
    from .nfl2k5_uniform_equipment_writer import EquipmentCompileCache, build_unified_uniform_equipment_imports
    cache = getattr(session, "_equipment_staging_cache", None)
    if cache is None:
        cache = session._equipment_staging_cache = EquipmentCompileCache()
    groups = defaultdict(list)
    for asset_id, path in sorted(paths.items()):
        t = by_id[asset_id]
        groups[t.outer_index, t.chunk_index].append((asset_id, path))
    rows = []
    for group in groups.values():
        compiled = build_unified_uniform_equipment_imports(
            session.cache.pack0, group, preflight_only=True, compile_cache=cache,
            fit_asset_id=selected if any(asset_id == selected for asset_id, _ in group) else None)
        for asset_id, _ in group:
            t = by_id[asset_id]
            rows.append(dict(compiled.edit_templates[t.reference_index], asset_id=asset_id,
                             set_selector=t.set_selector,
                             encoded_bytes=compiled.rebuild_info.recompressed_bytes))
    return rows


def equipment_fit_rows(session):
    """Current measured rows, including restored projects; never trust PNG hints.

    Call in a worker. The compile cache keys the complete physical group. A
    sibling edit, Undo or restore therefore cannot leave a stale fit caption.
    """
    from .nfl2k5_uniform_equipment_writer import load_targets
    by_id, _ = load_targets()
    paths = {}
    for edit in session.iter_edits():
        if edit.asset_id in by_id:
            _validate_staged(edit)
            paths[edit.asset_id] = edit.replacement_path
    return _checked_rows(session, paths, by_id)


def _validate_staged(edit):
    if not 0 < edit.replacement_path.stat().st_size <= 32 * 1024 * 1024:
        raise ValidationError("A staged equipment PNG exceeds the import size bound.")
    if hashlib.sha256(edit.replacement_path.read_bytes()).hexdigest() != edit.replacement_sha256:
        raise ValidationError("A staged equipment PNG changed outside Mod Studio.")


def stage_equipment_import(session, asset, path, *, independent=None, scale=1, scope=None):
    from .nfl2k5_uniform_equipment_writer import load_targets, encode_rgba_png
    by_id, _ = load_targets()
    target = by_id.get(asset.asset_id)
    if target is None or getattr(asset, "kind", None) != "uniform_equipment_texture":
        raise ValidationError("Choose a reviewed equipment texture.")
    choices, rule = equipment_import_scope(asset.asset_id)
    if scope is not None and scope not in {value for value, _ in choices}:
        raise ValidationError(rule)
    payload, rgba = session.asset_io.validate_replacement(asset, path)
    original, original_rgba = session.asset_io.validate_replacement(asset, session.asset_io.ensure_original(asset))
    if independent is None:
        independent = supports_own_texture(asset.asset_id) and rgba != original_rgba
    frozen = with_import_mode(payload, asset.asset_id, rgba, independent=independent, scale=scale)
    restoring = same_visual_import(asset, frozen, rgba, original, original_rgba)
    consumers = staging_targets(target, by_id)
    consumer_ids = tuple(t.asset_id for t in consumers)
    current = {}
    for edit in session.iter_edits():
        if edit.asset_id in by_id and edit.asset_id not in consumer_ids:
            _validate_staged(edit)
            current[edit.asset_id] = edit.replacement_path
    with tempfile.TemporaryDirectory(prefix="equipment-import-", dir=session.replacements) as directory:
        canonical = with_retail_source(encode_rgba_png(target.width, target.height, rgba),
                                       retail_source(frozen, rgba), rgba)
        replacements = []
        for t in consumers:
            copy = asset if t.asset_id == asset.asset_id else session._visual_asset(t.asset_id)
            if restoring:
                if session.is_modified(t.asset_id):
                    replacements.append((copy, session.asset_io.ensure_original(copy)))
                continue
            png = Path(directory) / f"{t.outer_index}_{t.chunk_index}_{t.reference_index}.png"
            png.write_bytes(with_import_mode(canonical, t.asset_id, rgba, independent=independent, scale=scale))
            replacements.append((copy, png))
            current[t.asset_id] = png
        # Both clean and mud share one span and one fit, before any mutation.
        checked = _checked_rows(session, current, by_id, selected=asset.asset_id)
        result = session.replace_batch(tuple(replacements), label="Import equipment texture")
    staged = tuple(t.asset_id for t, _ in replacements)
    receipt = {"schema": "nfl2k5_equipment_staging/v1", "edits": checked,
               "consumers": _consumer_receipt(target, consumers, () if restoring else staged),
               "normal_and_mud_staged_together": any(t.name == target.name + "_mud" for t in consumers),
               "in_game_outcome": "UNWITNESSED"}
    if restoring:
        message = f"Equipment artwork restored in {len(staged)} slots."
    else:
        row = next(r for r in checked if r["asset_id"] == asset.asset_id)
        fits = sorted({r["fit_summary"] for r in checked if r["asset_id"] in consumer_ids})
        message = f"Equipment artwork {row['fit_summary']}."
        if len(fits) > 1:
            message += " Other package fits: " + "; ".join(fits) + "."
        if receipt["normal_and_mud_staged_together"]:
            message += " Normal and mud artwork staged together."
        message += f" {len(consumers)} slots checked. {rule} In-game outcome UNWITNESSED."
    return EquipmentImportResult(message, receipt, result.changed_asset_ids,
                                 asset.asset_id in result.modified_asset_ids, consumer_ids)


def revert_equipment_import(session, asset):
    from .nfl2k5_uniform_equipment_writer import load_targets
    by_id, _ = load_targets()
    target = by_id.get(getattr(asset, "asset_id", None))
    if target is None:
        raise ValidationError("Choose a reviewed equipment texture.")
    replacements = []
    for t in staging_targets(target, by_id):
        if session.is_modified(t.asset_id):
            copy = asset if t.asset_id == asset.asset_id else session._visual_asset(t.asset_id)
            replacements.append((copy, session.asset_io.ensure_original(copy)))
    if not replacements:
        return ()
    return session.replace_batch(tuple(replacements), label=f"Revert {asset.label}").changed_asset_ids
