"""Portable fit measurements. Opening a project only hashes; Build compiles.

Receipts contain metadata, never encoded game bytes, and are advisory: the
builder independently verifies every emitted span. A physical group includes
all of its replacements so that a changed sibling invalidates the measurement.
"""
from __future__ import annotations

import hashlib
import json
import time


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def equipment_keys(index, edits, source_hash):
    from . import nfl2k5_uniform_equipment_writer as writer
    from .json_stream import read_bounded_regular_file
    groups = {}
    for edit in edits:
        if edit.asset_id.startswith('tset:'):
            group = tuple(map(int, edit.asset_id.split(':')[1:3]))
            groups.setdefault(group, []).append(edit)
    if not groups:
        return {}
    by_id, targets = writer.load_targets()
    compiler = writer._stage_compiler_key()
    archive = writer.parse_archive(index)
    result = {}
    # One package read per uniform set. No decode, mip generation or pack walk.
    for outer in sorted({group[0] for group in groups}):
        package = writer.read_entry_bytes(archive, archive.entries[outer])
        chunks = {c.index: c for c in writer.parse_chunks(package, allow_trailing=True)}
        for group in sorted(g for g in groups if g[0] == outer):
            chunk = chunks[group[1]]
            rows = groups[group]
            inputs = []
            for row in rows:
                _, payload = read_bounded_regular_file(row.replacement_path,
                    'Equipment replacement', maximum=32 * 1024 * 1024)
                actual = hashlib.sha256(payload).hexdigest()
                if actual != row.replacement_sha256:
                    from .errors import ValidationError
                    raise ValidationError(f'{row.asset_id}: staged PNG changed. Import it again.')
                inputs.append((row.asset_id, actual))
            key = digest(dict(source=source_hash, compiler=compiler,
                span=hashlib.sha256(package[chunk.offset:chunk.end_offset]).hexdigest(),
                target=writer._rows_signature(targets[group]), inputs=sorted(inputs)))
            for row in rows:
                result[row.asset_id] = key
    return result


def source_hash(session):
    return session.cache.source.sha256


def remember(session, rows):
    """Called after a completed fit transaction, never by a background open."""
    keys = equipment_keys(session.cache.pack0, session.iter_edits(), source_hash(session))
    receipts = dict(getattr(session, '_project_fit_receipts', {}))
    grouped = {}
    for row in rows:
        key = keys.get(row['asset_id'])
        if key is not None and row.get('fit_status') != 'fit pending':
            grouped.setdefault(key, []).append(dict(row))
    receipts.update(grouped)
    session._project_fit_receipts = receipts


def restore(session, receipts):
    from .equipment_staging import _remember_fit
    from .nfl2k5_uniform_equipment_writer import load_targets
    keys = equipment_keys(session.cache.pack0, session.iter_edits(), source_hash(session))
    targets, _ = load_targets() if keys else ({}, {})
    rows = []
    for asset_id, key in keys.items():
        row = next((r for r in receipts.get(key, ()) if r.get('asset_id') == asset_id), None)
        rows.append(dict(row) if row is not None else dict(asset_id=asset_id,
            set_selector=targets[asset_id].set_selector, fit_status='fit pending'))
    session._project_fit_receipts = dict(receipts)
    _remember_fit(session, rows, persist=False)
    restore_art(session, receipts)


def remember_art(session, records):
    """Bind a verified provider fit to the session's original authored paths."""
    edits = list(session.iter_project_png_edits())
    by_path = {str(e.replacement_path.resolve()): e for e in edits}
    receipts = dict(getattr(session, '_project_fit_receipts', {}))
    groups = {}
    for record in records:
        selected = [by_path[path] for path in record.get('paths', ()) if path in by_path]
        if not selected:
            continue
        inputs = {e.asset_id: e.replacement_sha256 for e in selected}
        group = groups.setdefault(digest(inputs), dict(inputs=inputs, targets=[]))
        group['targets'].extend(t for t in record['targets'] if t not in group['targets'])
    for group in groups.values():
        inputs = group['inputs']
        body = dict(kind='project_art', source=source_hash(session), inputs=inputs,
                    targets=group['targets'])
        key = digest(body)
        receipts[key] = [dict(body, asset_id=asset_id, fit_status='fits') for asset_id in inputs]
    session._project_fit_receipts = receipts
    restore_art(session, receipts)


def restore_art(session, receipts):
    """Hash just the recorded source spans. PNG validation happens in the loader."""
    from . import nfl2k5_uniform_equipment_writer as writer
    edits = {e.asset_id: e.replacement_sha256 for e in session.iter_project_png_edits()}
    accepted, spans = {}, {}
    packs = None
    for key, rows in receipts.items():
        if not rows or rows[0].get('kind') != 'project_art':
            continue
        row = rows[0]
        body = {k: row[k] for k in ('kind', 'source', 'inputs', 'targets')}
        if key != digest(body) or row['source'] != source_hash(session):
            continue
        if any(edits.get(asset_id) != value for asset_id, value in row['inputs'].items()):
            continue
        if packs is None:
            packs = {p.name: p for p in writer.parse_archive(session.cache.pack0).packs}
        valid = True
        for target in row['targets']:
            identity = (target['pack'], target['offset'], target['size'])
            if identity not in spans:
                pack = packs.get(target['pack'])
                if pack is None or not (0 <= target['offset'] < pack.size
                        and 0 < target['size'] <= min(64 * 1024 * 1024, pack.size - target['offset'])):
                    valid = False
                    break
                with pack.path.open('rb') as source:
                    source.seek(target['offset'])
                    spans[identity] = hashlib.sha256(source.read(target['size'])).hexdigest()
            if spans[identity] != target['sha256']:
                valid = False
                break
        if valid:
            accepted.update((r['asset_id'], r) for r in rows if r['asset_id'] in row['inputs'])
    session._art_fit_receipts = accepted
    session._art_fit_identity = edits


def art_fit_labels(session):
    if not hasattr(session, 'iter_project_png_edits'):
        return {}
    identity = getattr(session, '_art_fit_identity', {})
    receipts = getattr(session, '_art_fit_receipts', {})
    return {e.asset_id: ('fit checked at Build' if e.asset_id in receipts
                        and identity.get(e.asset_id) == e.replacement_sha256
                        else 'fit pending; checked when you build')
            for e in session.iter_project_png_edits() if not e.asset_id.startswith('tset:')}


def progress_text(stage, done, total, started):
    if total <= 0:
        return stage
    elapsed = max(0, time.monotonic() - started)
    eta = f'about {max(0, round(elapsed * (total - done) / done))} s remaining' if done else 'estimating time remaining'
    return f'{stage} • {done} of {total} • {eta}'


class BuildCancelled(Exception):
    """Cancellation is control flow, not an ignorable progress observer error."""


def check_cancelled(progress):
    event = getattr(progress, 'cancelled', None)
    if event is not None and event.is_set():
        raise BuildCancelled('Build cancelled; no output was published. Your project is unchanged.')
