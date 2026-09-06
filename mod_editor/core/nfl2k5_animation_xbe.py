"""EXPERIMENTAL / UNWITNESSED edits of two pinned occupied .rdata motion roots.

No cave, hook, allocator request or runtime storage. The default one-word edit
is an offline composition witness; user imports carry their own Replacement.
"""
from __future__ import annotations
from pathlib import Path
import json
import struct

from . import nfl2k5_animation as A
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage, MANIFEST_SCHEMA

OWNER = 'nfl2k5_animation_xbe'
REQUESTS = ()
CAVES = ()
RUNTIME_GLOBALS = ()
# header VA: (occupied span VA, byte count, SHA256 of complete original span)
PINS = {
    0x86dfe0: (0x86d478, 2972, 'c5e0c865cdb6b9f26d238311290f019e33f833f7b5f3f403018d6d48eea17b2a'),
    0x8528e8: (0x851e38, 2788, 'dd3667937fab95c93e265ef12300f24ce6d5aa9b5731d1204630b9351dad7999'),
}
DEFAULT_BEFORE = 0x2417f5da
DEFAULT_AFTER = 0x2417f5db


def reservations(payload=None):
    return [{'owner': OWNER, 'start': hex(va), 'end': hex(va+n), 'size': n,
             'basis': 'occupied retail motion root; fixed-span key edits only, never a cave'}
            for va, n, _ in PINS.values()]


def _reservation_check(manifest=None):
    if manifest is None:
        path = Path(__file__).resolve().parents[2]/'data/nfl2k5_cave_reservations.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
    A.require(manifest.get('complete') is True and manifest.get('retail_sha256') == A.RETAIL_XBE_SHA256,
              'Animation reservation manifest is incomplete or belongs to another executable')
    A.require(manifest.get('schema') == MANIFEST_SCHEMA and isinstance(manifest.get('spans'), list)
              and manifest['spans'], 'Invalid animation reservation manifest')
    for row in manifest['spans']:
        start, end = int(row['start'], 0), int(row['end'], 0)
        A.require(start < end and row.get('owner'), 'Invalid reservation bounds/owner')
        if row['owner'] == OWNER:
            # The manifest recorder also observes our section-header digest
            # writes (at different header VAs on retail and grown images).
            # Ownership does not widen this writer: _preflight pins the whole
            # root and permits only its main words; apply repins one digest.
            continue
        A.require(not any(start < va+n and va < end for va, n, _ in PINS.values()),
                  f'Animation data overlaps reserved owner {row["owner"]}')


def _site(payload, header):
    image = XbeImage(payload)
    A.require(header in PINS, 'Unproved embedded root')
    va, n, _ = PINS[header]
    section = image.section(va, n)
    A.require(section is not None and section.name == '.rdata' and section.flags == 7,
              'Animation root must retain the retail .rdata flags (7)')
    sections = _sections(payload)
    A.require(all(section_digest(payload, s) == s.stored_digest for s in sections), 'Stale XBE section digest')
    return image.offset(va, n), next(s for s in sections if s.header_offset == section.header)


def clip_from_span(header, raw, file_offset):
    va, n, digest = PINS[header]
    A.require(len(raw) == n and A.sha256(raw) == digest, 'Embedded original motion span is not retail')
    at = header-va
    channels, frames = raw[at], struct.unpack_from('<H', raw, at+2)[0]
    targets = dict(zip(('rotations', 'trajectory', 'events', 'auxiliary'), struct.unpack_from('<4I', raw, at+36)))
    regions = []
    for name, address in targets.items():
        if not address:
            continue
        start = address-va
        size = {'rotations': 4*channels*frames, 'trajectory': (6 if raw[at+4]&8 else 8)*frames,
                'auxiliary': 12*frames}.get(name)
        if name == 'events':
            end = start
            while end+4 <= len(raw) and raw[end:end+4] != b'\xff'*4:
                end += 4
            A.require(end+4 <= len(raw), 'Unterminated embedded events')
            size = end+4-start
        regions.append((name, start, start+size))
    root = A._root(raw, 0, at, regions, {name: a for name, a, _ in regions})
    return A.Clip(f'xbe:{header:08x}', f'Embedded root {header:08x}', 'XBE_ROOT',
                  {'scope': 'embedded_xbe', 'header_va': header, 'span_va': va, 'file_offset': file_offset,
                   'xbe_sha256': A.RETAIL_XBE_SHA256}, raw, raw, (root,), 'unknown', None,
                  {'header_hex': raw[at:at+52].hex(), 'pointer_mode': 'absolute_va'})


def default_replacement(payload):
    header = 0x86dfe0
    off, _ = _site(payload, header)
    _, n, _ = PINS[header]
    raw = bytearray(payload[off:off+n])
    A.require(struct.unpack_from('<I', raw, 200)[0] in (DEFAULT_BEFORE, DEFAULT_AFTER), 'Foreign embedded witness word')
    struct.pack_into('<I', raw, 200, DEFAULT_BEFORE)
    clip = clip_from_span(header, bytes(raw), off)
    keys = A.native_rotations(clip)
    keys[0][0] = A.qm.decode(DEFAULT_AFTER)
    return A.compile_replacement(clip, keys)


def _preflight(payload, replacement, manifest):
    _reservation_check(manifest)
    try:
        header = int(replacement.identity.removeprefix('xbe:'), 16)
        va, n, digest = PINS[header]
    except (ValueError, KeyError) as exc:
        raise A.AnimationError('Unproved embedded animation identity') from exc
    A.require(replacement.identity == f'xbe:{header:08x}', 'Noncanonical embedded identity')
    off, section = _site(payload, header)
    clip = clip_from_span(header, replacement.before, off)
    A.require(len(replacement.after) == n, 'Embedded replacement changes its span')
    r = clip.roots[0]
    for run in A._diff_spans(replacement.before, replacement.after):
        A.require(r.rotations <= run['offset'] and run['offset']+run['length'] <= r.rotations+4*r.frames*r.channels,
                  'Embedded replacement changes data outside primary rotation words')
    # Reject invalid encodings even for manually constructed Replacement objects.
    for i in range(r.frames*r.channels):
        A.qm.decode(struct.unpack_from('<I', replacement.after, r.rotations+i*4)[0])
    return off, section, replacement.status(payload[off:off+n])


def status(payload, replacement=None, *, manifest=None):
    try:
        replacement = replacement or default_replacement(payload)
        _, _, state = _preflight(payload, replacement, manifest)
        return 'retail' if state == 'original' else state
    except (ValueError, KeyError, TypeError, struct.error):
        return 'foreign'


def apply(payload, replacement=None, *, manifest=None):
    replacement = replacement or default_replacement(payload)
    off, section, state = _preflight(payload, replacement, manifest)
    output = bytearray(payload)
    output[off:off+len(replacement.after)] = replacement.after
    output[section.header_offset+36:section.header_offset+56] = section_digest(output, section)
    output = bytes(output)
    A.require(status(output, replacement, manifest=manifest) in ('applied', 'unchanged'), 'Embedded read-back failed')
    runs = A._diff_spans(payload, output)
    return output, {'schema': 'nfl2k5_animation_xbe/v1', 'status': 'applied', 'owner': OWNER,
                    'identity': replacement.identity, 'already_applied': state == 'applied',
                    'changed_bytes': sum(r['length'] for r in runs), 'write_spans': runs,
                    'sections_repinned': [section.index] if runs else [], 'reservations': reservations(),
                    'edits': [{'label': 'occupied embedded motion span', 'va': row['start'], 'bytes': row['size']}
                              for row in reservations()], 'experimental': True, 'witnessed': False}


def write_import_copy(plan, source, destination):
    from .nfl2k5_animation_import import _read, SpanEdit, write_copy
    A.require(plan.clip.kind == 'XBE_ROOT' and plan.receipt.get('preflight_passed'), 'Embedded preflight is missing')
    before = _read(source)
    after, receipt = apply(before, plan.replacement)
    edit = SpanEdit(plan.clip.identity, before, after, ((0, 0, len(before)),))
    return write_copy(source, destination, (edit,), receipt={**plan.receipt, 'xbe': receipt})
