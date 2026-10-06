#!/usr/bin/env python3
"""Copy-only retirement of v0.4's incomplete practice squad. No disc rebuild.

Only default.xbe is touched. A composed integration input requires its exact
independently recorded SHA-256 via --expected-input-sha256; functional spans
still must match the pinned v0.4 bytes (or the exact retired bytes).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core.nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

V04_SHA256 = '5a9dc534b50c7f13b5124bfff9e39c99f96f62be4cc1de33309895c330c75f29'
# Filled from the native scoped replay; no game data is distributed here.
FIXED_SHA256 = '16f312e4a5de98ea5be0c7bb9e909f2a10e5794c714bfdfbfd771f7aa9b6d00f'
SITES = (
    ('preseason_cut_to_free_agency', 0x2BFA6E, bytes.fromhex('e83d871200'), bytes.fromhex('e88ddeffff')),
    ('coach_desk_schedule_practice_crib', 0x5221A0, bytes.fromhex('58294e01'), bytes.fromhex('ec1e5200')),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def repair(payload: bytes, *, expected_input_sha256: str | None = None):
    before_hash = digest(payload)
    accepted = {V04_SHA256, FIXED_SHA256}
    if expected_input_sha256 is not None:
        if len(expected_input_sha256) != 64 or any(c not in '0123456789abcdef' for c in expected_input_sha256):
            raise ValueError('expected input hash must be a lowercase SHA-256')
        accepted = {expected_input_sha256}
    if before_hash not in accepted:
        raise ValueError('unexpected input SHA-256; an integrator must pin the composed input explicitly')
    image, sections = XbeImage(payload), _sections(payload)
    out, ranges, touched = bytearray(payload), [], set()
    for label, va, before, after in SITES:
        at = image.offset(va, len(before))
        got = payload[at:at + len(before)]
        if got not in (before, after):
            raise ValueError(f'{label}: unexpected bytes at {va:#x}; refusing')
        section = _section_for_offset(sections, at)
        if section.stored_digest != section_digest(payload, section):
            raise ValueError(f'{label}: invalid input section digest')
        out[at:at + len(after)] = after
        touched.add(section.index)
        ranges.append(dict(label=label, va=f'{va:#x}', offset=at, size=len(after),
                           before=got.hex(), after=after.hex()))
    for section in sections:
        if section.index in touched:
            at = section.header_offset + 36
            out[at:at + 20] = section_digest(out, section)
            ranges.append(dict(label=f'section_{section.index}_sha1', offset=at, size=20,
                               before=payload[at:at + 20].hex(), after=out[at:at + 20].hex()))
    result = bytes(out)
    if before_hash == V04_SHA256 and digest(result) != FIXED_SHA256:
        raise ValueError('canonical v0.4 repair output differs from its pinned hash')
    ordered = sorted(ranges, key=lambda row: row['offset'])
    before_outside, after_outside = hashlib.sha256(), hashlib.sha256()
    cursor = 0
    for row in ordered:
        start, end = row['offset'], row['offset'] + row['size']
        if start < cursor:
            raise ValueError('overlapping repair scope')
        if payload[cursor:start] != result[cursor:start]:
            raise ValueError('outside-scope byte changed')
        before_outside.update(payload[cursor:start]); after_outside.update(result[cursor:start])
        cursor = end
    if payload[cursor:] != result[cursor:]:
        raise ValueError('outside-scope tail changed')
    before_outside.update(payload[cursor:]); after_outside.update(result[cursor:])
    receipt = dict(schema='b765-p1-native-repair/v1', disc_files=['default.xbe'],
        before_sha256=before_hash, after_sha256=digest(result), size=len(result),
        already_applied=result == payload, changed_bytes=sum(a != b for a, b in zip(payload, result)),
        ranges=ordered, new_code_caves=[], save_changes=False, gameplay_witnessed=False,
        outside_scope_identical=True, outside_scope_bytes=len(payload) - sum(r['size'] for r in ranges),
        outside_before_sha256=before_outside.hexdigest(), outside_after_sha256=after_outside.hexdigest(),
        composed_input=before_hash not in (V04_SHA256, FIXED_SHA256))
    return result, receipt


def write_copy(output: Path, content: bytes):
    if output.exists():
        if output.is_symlink() or output.read_bytes() != content:
            raise ValueError('output exists with different bytes; refusing to overwrite')
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=output.name + '.', dir=output.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        # Publish without overwriting an output created concurrently.
        os.link(name, output)
    finally:
        Path(name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-xbe', required=True, type=Path)
    parser.add_argument('--output-xbe', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--expected-input-sha256')
    args = parser.parse_args()
    if args.input_xbe.resolve() == args.output_xbe.resolve():
        parser.error('output must be a separate copy')
    try:
        fixed, receipt = repair(args.input_xbe.read_bytes(), expected_input_sha256=args.expected_input_sha256)
        write_copy(args.output_xbe, fixed)
        write_copy(args.receipt, (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode())
        print(json.dumps(receipt, indent=2, sort_keys=True))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'p1 repair refused: {exc}\n')


if __name__ == '__main__':
    main()
