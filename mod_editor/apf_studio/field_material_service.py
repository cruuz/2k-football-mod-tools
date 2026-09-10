"""Portable scalar-only field opacity recipes with atomic staging and Undo."""
from __future__ import annotations
import json
from mod_editor.core import apf_field_material_writer as writer
from mod_editor.core.errors import ValidationError
from .models import Modification

PROVIDER_KIND = writer.PROVIDER_KIND
SCHEMA = writer.SCHEMA


def selector(outer: int) -> str:
    if type(outer) is not int or outer not in writer.ENTRY_NAME_IDS:
        raise ValidationError("Choose a supported field entry")
    return f"field-material:{outer}"


def validate_metadata(asset_id, value):
    if not isinstance(value, dict) or set(value) != {'schema', 'outer_index'} or value['schema'] != SCHEMA:
        raise ValidationError('Field opacity metadata changed')
    if asset_id != selector(value['outer_index']):
        raise ValidationError('Field opacity asset identity changed')
    return value


def encode(outer, alphas):
    selector(outer)
    return (json.dumps({'schema': SCHEMA, 'outer_index': outer, 'alphas': writer.normalize_alphas(alphas)},
                       sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def validate_payload(data, asset_id, metadata):
    validate_metadata(asset_id, metadata)
    try:
        value = json.loads(data)
        if (not isinstance(value, dict) or set(value) != {'schema', 'outer_index', 'alphas'}
                or {k: value[k] for k in metadata} != metadata
                or encode(value['outer_index'], value['alphas']) != data):
            raise ValidationError('Field opacity recipe is not canonical')
        return value
    except (ValueError, TypeError, KeyError) as exc:
        raise ValidationError(f'Invalid field opacity recipe: {exc}') from exc


def read_profile(modification):
    if modification.kind != PROVIDER_KIND:
        raise ValidationError('Expected a field opacity recipe')
    data = modification.replacement_path.read_bytes()
    if writer.sha(data) != modification.replacement_sha256:
        raise ValidationError('Field opacity payload changed after staging')
    return validate_payload(data, modification.asset_id, dict(modification.metadata))


def stage_profile(session, outer, alphas):
    payload = encode(outer, alphas)
    digest = writer.sha(payload)
    _, report = writer.build_patch(session.source.index_0a, outer, alphas)
    asset_id = selector(outer)
    previous = session._modifications.get(asset_id)
    if previous is not None and previous.replacement_sha256 == digest:
        return report
    stored = session._store_payload(digest, payload, '.json')
    session._record_undo()
    session._modifications[asset_id] = Modification(asset_id, PROVIDER_KIND, stored, digest,
                                                   {'schema': SCHEMA, 'outer_index': outer})
    return report


def context(session, outer):
    selector(outer)
    archive = writer.apf_outer.parse_archive(session.source.index_0a)
    entry = archive.entries[outer]
    if entry.name_id != writer.ENTRY_NAME_IDS[outer]:
        raise ValidationError('Field entry identity changed')
    with writer.apf_inner.ArchiveReader(archive) as reader:
        original = reader.read(entry, 0, entry.size)
    _, part, block = writer._parse_entry(entry, original)
    materials = writer.parse_scene(block[part.offset:part.offset+part.length])
    modification = session._modifications.get(selector(outer))
    staged = {} if modification is None else read_profile(modification)['alphas']
    return materials, staged


def compile_modification(index, modification, current_entry=None):
    value = read_profile(modification)
    return writer.build_patch(index, value['outer_index'], value['alphas'], current_entry=current_entry)
