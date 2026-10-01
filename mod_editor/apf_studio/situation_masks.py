"""Situation patch transport shared by project builds, export and installation."""
from __future__ import annotations
import json
from pathlib import Path
from mod_editor.core.errors import ValidationError
from mod_editor.core import apf2k8_situation_mask as native

FILENAME = '54540807 - Studio situation exclusions.patch.toml'


def policy_data(state):
    masks, rows, weights = state.situation_masks, state.situation_personnel_rows, state.situation_formation_weights
    modern = bool(weights) or any(len(r) == 13 for p in (masks, rows) for r in p.values())
    return native.encode_data(masks, rows, weights if modern else None)


def prepare(state, profile_name):
    profile = next((p for p in native.PROFILES if p.name == profile_name), None)
    if profile is None:
        raise ValidationError('Choose BASE or TU 1.1 for the situation patch')
    document = native.SituationPatch(profile, policy_data(state) if state.situation_masks_enabled else native.encode_data({}, {}))
    payload = document.as_toml().encode('utf-8')
    native.canonical_payload(payload)
    return {'payload': payload, 'receipt': document.receipt, 'profile': profile_name}


def export_build(directory, state):
    if not state.situation_masks_enabled or not (state.situation_masks or state.situation_personnel_rows or state.situation_formation_weights):
        return None
    receipts = []
    for profile in native.PROFILES:
        prepared = prepare(state, profile.name)
        target = Path(directory) / f'54540807-situations-{profile.name}.patch.toml'
        target.write_bytes(prepared['payload'])
        native.canonical_payload(target.read_bytes())
        if target.read_bytes() != prepared['payload']:
            raise ValidationError('Situation patch failed build readback')
        receipts.append({**prepared['receipt'], 'file': target.name})
    data = policy_data(state)
    keys = 13 if native.SituationPatch(native.PROFILES[0], data).version == 3 else 12
    target = Path(directory) / 'situation-masks.bin'
    target.write_bytes(data)
    if native.decode_data(target.read_bytes()) != native.canonical_policies(state.situation_masks, key_count=keys):
        raise ValidationError('Situation data failed build readback')
    if native.decode_personnel_rows(target.read_bytes()) != native.canonical_personnel_rows(state.situation_personnel_rows, key_count=keys):
        raise ValidationError('Personnel rows failed build readback')
    if native.decode_formation_weights(target.read_bytes()) != native.canonical_formation_weights(state.situation_formation_weights):
        raise ValidationError('Formation weights failed build readback')
    result = {'patches': receipts, 'data': target.name,
              'next_step': 'Install the patch for the executable version you launch. Book data alone does not enable exclusions, personnel-row overrides or formation multipliers.',
              'runtime_status': 'UNWITNESSED'}
    (Path(directory) / 'situation-mask-receipt.json').write_bytes((json.dumps(result, indent=2)+'\n').encode())
    return result
