"""Atomic equipment staging, including a normal variant's dirty sibling.

The UI enters here. Consumer resolution and legacy import contracts stay in
their existing modules; one combined compile supplies the actual fit receipt.
"""
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
    from .nfl2k5_uniform_equipment_writer import preflight_project_equipment
    rows = preflight_project_equipment(session.cache.pack0,
        [(None, asset_id, path) for asset_id, path in sorted(paths.items())])
    if selected is not None:
        row = next((r for r in rows if r['asset_id'] == selected), None)
        if row is not None and row.get('fit_status') == 'needs refit':
            _raise_fit(row)
    return rows


def _raise_fit(row):
    from .nfl2k5_uniform_equipment_writer import EquipmentFitError, EquipmentRefitError
    if row.get('budget') is None:
        raise EquipmentRefitError(row['fit_error'])
    raise EquipmentFitError(row['budget'], row['required'], row['attempts'], row['suggestion'],
                            required_is_lower_bound=row['required_is_lower_bound'])


def require_equipment_fit(session):
    """Build gate: check current bytes and name only edits still needing refit."""
    if not any(key.startswith('tset:') for key in session.modified_asset_ids):
        return
    failed = [r for r in equipment_fit_rows(session) if r.get('fit_status') == 'needs refit']
    if failed:
        raise ValidationError('\n'.join(
            f"Cannot build Equipment / uniform set {r['set_selector']} / {r['asset_id']}: "
            f"needs refit: {r['fit_error']} Use Refit equipment in Build, or revert this item."
            for r in failed))


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
    rows = _checked_rows(session, paths, by_id)
    _remember_fit(session, rows)
    return rows


def _fit_identity(session):
    return tuple(sorted((e.asset_id, e.replacement_sha256) for e in session.iter_edits()
                        if e.asset_id.startswith("tset:")))


def _remember_fit(session, rows):
    from collections import OrderedDict
    cache = getattr(session, "_equipment_fit_receipts", None)
    if cache is None:
        cache = session._equipment_fit_receipts = OrderedDict()
    key = _fit_identity(session)
    cache[key] = tuple(dict(row) for row in rows)
    cache.move_to_end(key)
    while len(cache) > 8:
        cache.popitem(last=False)


def cached_equipment_fit_rows(session):
    """Cheap GUI captions for this exact staged group; stale results disappear.

    Import and worker-side restored-project checks populate this cache. An
    unmeasured project returns no rows and must say that its fit is pending.
    Build always compiles/checks the bytes independently.
    """
    cache = getattr(session, "_equipment_fit_receipts", None)
    if not cache:
        return ()
    rows = cache.get(_fit_identity(session), ())
    return tuple(dict(row) for row in rows)


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
        # Keep each variant's fit status, including an existing unresolved sibling.
        checked = _checked_rows(session, current, by_id, selected=asset.asset_id)
        result = session.replace_batch(tuple(replacements), label="Import equipment texture")
        _remember_fit(session, checked)
    staged = tuple(t.asset_id for t, _ in replacements)
    receipt = {"schema": "nfl2k5_equipment_staging/v1", "edits": checked,
               "consumers": _consumer_receipt(target, consumers, () if restoring else staged),
               "normal_and_mud_staged_together": any(t.name == target.name + "_mud" for t in consumers),
               "in_game_outcome": "UNWITNESSED"}
    if restoring:
        message = f"Equipment artwork restored in {len(staged)} slots."
    else:
        row = next(r for r in checked if r["asset_id"] == asset.asset_id)
        from .equipment_reporting import fit_caption
        fits = sorted({fit_caption(r) for r in checked if r["asset_id"] in consumer_ids})
        message = f"Equipment artwork {row['fit_summary']}."
        if row.get("palette_method") == "preserved_retail":
            message += " Retail palette and distance images preserved exactly."
        if len(fits) > 1:
            message += " Other package fits: " + "; ".join(fits) + "."
        if receipt["normal_and_mud_staged_together"]:
            message += " Normal and mud artwork staged together."
        packages = len({t.outer_index for t in consumers})
        message += (f" {len(consumers)} slots checked across {packages} uniform packages. "
                    f"{rule} In-game outcome UNWITNESSED.")
    return EquipmentImportResult(message, receipt, result.changed_asset_ids,
                                 asset.asset_id in result.modified_asset_ids, consumer_ids)


def refit_equipment(session, asset_id):
    """One explicit, undoable reduction: colours at the current size, then size.

    Rewrites only this item's authored PNG. Shared spans are checked with every
    currently fitting sibling; unresolved siblings retain their original bytes.
    """
    from . import nfl2k5_uniform_equipment_writer as writer
    from .nfl2k5_equipment_import_intent import import_settings, OWN_TEXTURE
    from .nfl2k5_digit_texture import make_digit_mips
    by_id, _ = writer.load_targets()
    target = by_id.get(asset_id)
    edits = {e.asset_id: e for e in session.iter_edits() if e.asset_id in by_id}
    if target is None or asset_id not in edits:
        raise ValidationError('Choose a staged equipment item to refit.')
    for edit in edits.values():
        _validate_staged(edit)
    asset = session._visual_asset(asset_id)
    payload, rgba = session.asset_io.validate_replacement(asset, edits[asset_id].replacement_path)
    mode, current_scale = import_settings(payload, asset_id, rgba)
    independent = mode == OWN_TEXTURE
    measured = equipment_fit_rows(session)
    ready = {r['asset_id'] for r in measured if r.get('fit_status') != 'needs refit'}
    group = [(key, edit.replacement_path) for key, edit in edits.items()
             if key != asset_id and key in ready
             and (by_id[key].outer_index, by_id[key].chunk_index)
                 == (target.outer_index, target.chunk_index)]
    levels = make_digit_mips(rgba, target.width, target.height, target.mip_levels)
    seen = set()
    last = None
    with tempfile.TemporaryDirectory(prefix='equipment-refit-', dir=session.replacements) as directory:
        png = Path(directory) / 'refit.png'
        for scale in ((s for s in (1, 2, 4) if s >= current_scale) if independent else (1,)):
            for limit in writer.PALETTE_LIMITS:
                palette, indices, _ = writer._quantize_art(levels[:1], limit)
                reduced = b''.join(bytes(palette[i]) for i in indices[0])
                candidate = with_import_mode(writer.encode_rgba_png(target.width, target.height, reduced),
                    asset_id, reduced, independent=independent, scale=scale)
                digest = hashlib.sha256(candidate).digest()
                if digest in seen:
                    continue
                seen.add(digest)
                png.write_bytes(candidate)
                try:
                    compiled = writer.build_unified_uniform_equipment_imports(session.cache.pack0,
                        group + [(asset_id, png)], preflight_only=True, fit_asset_id=asset_id)
                except writer.EquipmentRefitError as exc:
                    last = exc
                    continue
                row = compiled.edit_templates[target.reference_index]
                result = session.replace_batch(((asset, png),), label='Refit equipment')
                checked = equipment_fit_rows(session)
                message = (f"Equipment {target.set_selector} / {target.name} {row['fit_summary']}; "
                           f"{compiled.rebuild_info.recompressed_bytes:,} bytes encoded. "
                           "Fine detail and shades may change. Undo restores the original artwork.")
                return EquipmentImportResult(message, {'edits': checked}, result.changed_asset_ids,
                    asset_id in result.modified_asset_ids, (asset_id,))
    raise ValidationError(f'Refit could not find a fitting colour count or size. {last}')


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
