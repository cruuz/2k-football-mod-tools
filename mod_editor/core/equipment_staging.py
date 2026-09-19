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
    from types import SimpleNamespace
    from .nfl2k5_uniform_equipment_writer import preflight_project_equipment, staged_equipment_cache
    staged_equipment_cache().size_for_project(len(paths))
    from .nfl2k5_project_fit import equipment_keys, source_hash
    edits = [SimpleNamespace(asset_id=asset_id, replacement_path=path,
                             replacement_sha256=_verified_art(session, path))
             for asset_id, path in sorted(paths.items())]
    keys = equipment_keys(session.cache.pack0, edits, source_hash(session), session=session)
    groups = {}
    for edit in edits:
        group = tuple(map(int, edit.asset_id.split(':')[1:3]))
        groups.setdefault(group, []).append(edit)
    previous = getattr(session, '_equipment_checked_groups', {})
    from .nfl2k5_equipment_lz import optimal_fit_is_capped
    capped = optimal_fit_is_capped()
    current, rows, changed = {}, [], []
    for group, items in groups.items():
        key = keys[items[0].asset_id]
        cached = previous.get(group)
        # A quick check's "fit pending" is not a measurement; an uncapped
        # caller (Refit equipment) measures that group to its real result.
        if (cached is not None and cached[0] == key
                and (capped or all(row.get('fit_status') != 'fit pending' for row in cached[1]))):
            current[group] = cached
            rows.extend(dict(row) for row in cached[1])
        else:
            changed.extend((None, item.asset_id, item.replacement_path) for item in items)
    if changed:
        checked = preflight_project_equipment(session.cache.pack0, changed)
        rows.extend(checked)
        for group, items in groups.items():
            if group not in current:
                ids = {item.asset_id for item in items}
                current[group] = (keys[items[0].asset_id], tuple(dict(row) for row in checked if row['asset_id'] in ids))
    session._equipment_checked_groups = current
    rows.sort(key=lambda row: row['asset_id'])
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
            _validate_staged(edit, session)
            paths[edit.asset_id] = edit.replacement_path
    rows = _checked_rows(session, paths, by_id)
    _remember_fit(session, rows)
    return rows


def _fit_identity(session):
    return tuple(sorted((e.asset_id, e.replacement_sha256) for e in session.iter_edits()
                        if e.asset_id.startswith("tset:")))


def _remember_fit(session, rows, *, persist=True, staged_ids=()):
    # replace_batch just wrote and hashed these exact validated bytes. Bind
    # their filesystem identity now; later calls hash only a changed identity.
    staged_ids = set(staged_ids)
    for edit in session.iter_edits():
        if edit.asset_id in staged_ids:
            _verified_art(session, edit.replacement_path, trusted_digest=edit.replacement_sha256)
    from collections import OrderedDict
    cache = getattr(session, "_equipment_fit_receipts", None)
    if cache is None:
        cache = session._equipment_fit_receipts = OrderedDict()
    key = _fit_identity(session)
    cache[key] = tuple(dict(row) for row in rows)
    cache.move_to_end(key)
    while len(cache) > 8:
        cache.popitem(last=False)
    if persist:
        from .nfl2k5_project_fit import remember
        remember(session, rows)


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


def _verified_art(session, path, *, expected=None, trusted_digest=None):
    from .json_stream import require_regular_file, read_bounded_regular_file
    path = Path(path)
    info = require_regular_file(path, 'Staged equipment PNG')
    if not 0 < info.st_size <= 32 * 1024 * 1024:
        raise ValidationError('A staged equipment PNG exceeds the import size bound.')
    identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    cache = getattr(session, '_equipment_art_identities', None)
    if cache is None:
        cache = session._equipment_art_identities = {}
    key = str(path.absolute())
    previous = cache.get(key)
    if trusted_digest is not None:
        actual = trusted_digest
    elif previous is not None and previous[0] == identity:
        actual = previous[1]
    else:
        _, payload = read_bounded_regular_file(path, 'Staged equipment PNG', maximum=32 * 1024 * 1024)
        actual = hashlib.sha256(payload).hexdigest()
    if expected is not None and actual != expected:
        raise ValidationError('A staged equipment PNG changed outside Mod Studio.')
    cache[key] = (identity, actual)
    return actual


def _validate_staged(edit, session):
    return _verified_art(session, edit.replacement_path, expected=edit.replacement_sha256)


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
            _validate_staged(edit, session)
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
        _remember_fit(session, checked, staged_ids=result.changed_asset_ids)
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
        message = (f"Equipment artwork {row['fit_summary']}." if row.get("fit_status") == "fits" else
                   "Equipment artwork staged. The quick check ran out of time, so Build finishes "
                   "its fit and refits it only if it cannot fit.")
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
    The ladder and its checks are ``writer.refit_item``, the same code Build
    uses when it refits an item automatically, and no clock stops the search.
    """
    from . import nfl2k5_uniform_equipment_writer as writer
    from .nfl2k5_equipment_lz import uncapped_optimal_fit
    by_id, _ = writer.load_targets()
    target = by_id.get(asset_id)
    edits = {e.asset_id: e for e in session.iter_edits() if e.asset_id in by_id}
    if target is None or asset_id not in edits:
        raise ValidationError('Choose a staged equipment item to refit.')
    for edit in edits.values():
        _validate_staged(edit, session)
    asset = session._visual_asset(asset_id)
    payload, rgba = session.asset_io.validate_replacement(asset, edits[asset_id].replacement_path)
    with uncapped_optimal_fit():
        measured = equipment_fit_rows(session)
        ready = {r['asset_id'] for r in measured if r.get('fit_status') != 'needs refit'}
        group = [(key, edit.replacement_path) for key, edit in edits.items()
                 if key != asset_id and key in ready
                 and (by_id[key].outer_index, by_id[key].chunk_index)
                     == (target.outer_index, target.chunk_index)]
        with tempfile.TemporaryDirectory(prefix='equipment-refit-', dir=session.replacements) as directory:
            def accept(png, _compiled):
                prospective = {key: edit.replacement_path for key, edit in edits.items()}
                prospective[asset_id] = png
                return _checked_rows(session, prospective, by_id, selected=asset_id)
            try:
                _candidate, compiled, checked = writer.refit_item(
                    session.cache.pack0, asset_id, payload, rgba, group, Path(directory), accept=accept)
            except writer.EquipmentRefitError as exc:
                raise ValidationError(str(exc)) from exc
            png = Path(directory) / 'refit.png'
            row = compiled.edit_templates[target.reference_index]
            result = session.replace_batch(((asset, png),), label='Refit equipment')
            _remember_fit(session, checked, staged_ids=result.changed_asset_ids)
            message = (f"Equipment {target.set_selector} / {target.name} {row['fit_summary']}; "
                       f"{compiled.rebuild_info.recompressed_bytes:,} bytes encoded. "
                       "Fine detail and shades may change. Undo restores the original artwork.")
            return EquipmentImportResult(message, {'edits': checked}, result.changed_asset_ids,
                asset_id in result.modified_asset_ids, (asset_id,))


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
