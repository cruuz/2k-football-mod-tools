#!/usr/bin/env python3
"""Validate or install the pinned uniform-card import spans on a staged 128 MB disc, including all 190 source slots."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_menu_helmet_w2026 as slots, platform_compat
from nfl2k5_playbook_position_recode import OuterImage

PINS = ROOT / 'data/nfl2k5_b81_uniform_cards.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stored(span):
    indices, palette, video = slots.read_slot(span)
    return sha(palette[indices].astype(np.uint8).tobytes()), video


def load_pins(path=PINS):
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    if doc['schema'] != 'nfl2k5_b81_uniform_card_outputs/v1' or len(doc['cards']) != 190:
        raise ValueError('Expected the complete 190-card beta 81 uniform document')
    return doc['cards']


def plan_archive(archive, payload, pins):
    writes, checked = [], {}
    for name, pin in sorted(pins.items()):
        at, old = slots.locate(archive, 'logos', name.removesuffix('_256'))
        current, video = stored(old)
        source, candidate = pin['source_native_sha256'], pin['stored_rgba_sha256']
        if current not in (source, candidate):
            raise ValueError(
                f'{name}: foreign stored RGBA, expected {source} or {candidate}, found {current}'
            )
        # The compiler first uses this same preflight to derive the full-slot pins from the donor.
        # The install document includes them, covering descriptors, palette indices and trailing padding.
        raw_pin = pin.get('new_slot_sha256' if current == candidate else 'reviewed_slot_sha256')
        if raw_pin is not None and sha(old) != raw_pin:
            raise ValueError(f'{name}: full card slot differs from its reviewed bytes')
        after = None
        if pin['replacement_sha256']:
            target = (payload / 'native' / (name + '.txtr.bin')).read_bytes()
            if (
                sha(target) != pin['replacement_sha256']
                or len(target) != pin['replacement_size']
                or not video < len(target) <= len(old)
            ):
                raise ValueError(f'{name}: failed normal importer span pin or size')
            if old[:video] != target[:video]:
                raise ValueError(f'{name}: disc wrapper or descriptors differ from the normal import')
            after = target + old[len(target) :]
            if stored(after)[0] != candidate:
                raise ValueError(f'{name}: imported span does not match its approved stored colors')
            if pin.get('new_slot_sha256') and sha(after) != pin['new_slot_sha256']:
                raise ValueError(f'{name}: full replacement card differs from its pin')
        if current != candidate:
            if after is None:
                raise ValueError(f'{name}: missing replacement')
            writes.append((name, at, old, after))
        checked[name] = {
            'actual_rgba_sha256': current,
            'reviewed_rgba_sha256': source,
            'expected_rgba_sha256': candidate,
            'status': 'unchanged'
            if source == candidate
            else 'installed'
            if current == candidate
            else 'ready',
        }
    return writes, checked


def update_archive(archive, payload, pins, *, write=False):
    plan, before = plan_archive(archive, payload, pins)
    result = {
        'schema': 'nfl2k5_b81_uniform_card_disc_readback/v1',
        'checked': len(before),
        'pending': len(plan),
        'written': 0,
        'source': before,
    }
    if not write:
        return result
    attempted = []
    try:
        for name, at, old, after in plan:
            if archive.read(at, len(old)) != old:
                raise ValueError(f'{name}: disc changed after preflight')
            attempted.append((at, old))
            if archive.write(at, after) != len(after) or archive.read(at, len(after)) != after:
                raise OSError(f'{name}: short write or complete-slot readback mismatch')
        final = {}
        for name, pin in pins.items():
            at, slot = slots.locate(archive, 'logos', name.removesuffix('_256'))
            actual, _ = stored(slot)
            if actual != pin['stored_rgba_sha256']:
                raise ValueError(f'{name}: the final stored RGBA differs after write')
            if pin.get('new_slot_sha256') and sha(slot) != pin['new_slot_sha256']:
                raise ValueError(f'{name}: the final complete slot differs after write')
            final[name] = actual
        result.update(written=len(plan), pending=0, final=final)
    except BaseException as error:
        failures = []
        for at, old in reversed(attempted):
            try:
                if archive.write(at, old) != len(old) or archive.read(at, len(old)) != old:
                    failures.append(hex(at))
            except OSError:
                failures.append(hex(at))
        if failures:
            raise OSError(f'Could not restore the card slots at {", ".join(failures)}') from error
        raise
    return result


def apply_to_image(image, payload, *, write=False, pins=PINS):
    image, payload = Path(image), Path(payload)
    with OuterImage(image, writable=write) as archive:
        if write:
            platform_compat.exclusive_nonblocking_lock(archive._fd)  # held through fsync and close
        return update_archive(archive, payload, load_pins(pins), write=write)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('--payload', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--receipt', type=Path)
    a = p.parse_args()
    report = apply_to_image(a.image, a.payload, write=a.apply)
    if a.receipt:
        a.receipt.write_text(json.dumps(report, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print(f"{report['checked']} cards checked, {report['written']} written, {report['pending']} pending")
