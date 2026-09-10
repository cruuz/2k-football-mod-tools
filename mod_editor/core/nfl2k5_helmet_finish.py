"""ADVANCED / UNWITNESSED helmet reflection weight, reversible to retail.

The native refresh selects shell A, B and C for either LOD. Redirect their
three conditional branches to its existing zero-weight clamp/store. The
fourth material retains the original lighting path. No cave or state is used.
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = 'nfl2k5_helmet_finish'
CAVES = RUNTIME_GLOBALS = REQUESTS = ()
FUNCTION_VA, FUNCTION_SIZE = 0x8FAD0, 263
FUNCTION_SHA256 = '84f7597e32b47cdc60663c2a461be107252059d6f38d18c8c948b1ebf90781b1'
SITES = ((0x8FB43, b'\x74\x21', b'\x74\x59'),
         (0x8FB4E, b'\x74\x16', b'\x74\x4e'),
         (0x8FB59, b'\x74\x0b', b'\x74\x43'))
HELP_TEXT = ('ADVANCED / UNWITNESSED. Glossy (retail) keeps the native helmet '
             'reflection weight. Matte sets the A/B/C shell reflection weight '
             'to zero during material refresh in both LODs. Default: Glossy (retail).')


def normalize_refresh(blob):
    """Shared dependency guard: accept only a complete retail or matte triple."""
    result, states = bytearray(blob), set()
    for va, before, after in SITES:
        at = va - FUNCTION_VA
        actual = result[at:at+len(before)]
        if actual not in (before, after):
            raise ValueError('Foreign helmet finish branch')
        states.add(bytes(actual) == after)
        result[at:at+len(before)] = before
    if len(states) != 1:
        raise ValueError('Mixed helmet finish branches')
    return result, 'applied' if states.pop() else 'retail'


def status(payload):
    try:
        image = XbeImage(payload)
        blob, state = normalize_refresh(image.read(FUNCTION_VA, FUNCTION_SIZE))
        from . import nfl2k5_guardian_overlay as guardian
        va, before = guardian.HOOKS['shine']
        if image.read(va, len(before)) != before:
            # Guardian's dependency guard normalizes only our exact triple;
            # its complete hooks and allocated code must still verify.
            if guardian.status(payload) != 'applied':
                return 'foreign'
            blob[va-FUNCTION_VA:va-FUNCTION_VA+len(before)] = before
        return state if hashlib.sha256(blob).hexdigest() == FUNCTION_SHA256 else 'foreign'
    except (ValueError, IndexError, struct.error):
        return 'foreign'


def verify(payload, *, finish='matte'):
    if finish not in ('glossy', 'matte'):
        raise ValueError('Helmet finish must be glossy or matte')
    state = status(payload)
    if state != ('applied' if finish == 'matte' else 'retail'):
        raise ValueError('Helmet finish does not match the requested complete installation')
    return dict(finish=finish, state=state, runtime_witnessed=False)


def apply(payload, *, finish='matte'):
    if finish not in ('glossy', 'matte'):
        raise ValueError('Helmet finish must be glossy or matte')
    state = status(payload)
    if state == 'foreign':
        raise ValueError('Foreign or mixed helmet material refresh; rebuild from base')
    image, result = XbeImage(payload), bytearray(payload)
    for va, before, after in SITES:
        at = image.offset(va, len(before))
        result[at:at+len(before)] = after if finish == 'matte' else before
    for s in _sections(result):
        result[s.header_offset+36:s.header_offset+56] = section_digest(result, s)
    result = bytes(result)
    receipt = verify(result, finish=finish)
    return result, dict(receipt, changed_bytes=sum(a != b for a, b in zip(payload, result)),
                        edits=[dict(va=hex(va), size=len(before)) for va, before, _ in SITES])


def reservations(payload):
    verify(payload)
    return [dict(owner=OWNER, start=hex(va), end=hex(va+len(before)), size=len(before),
                 basis='pinned live branch: helmet shell zero reflection weight')
            for va, before, _ in SITES]


def main(argv=None):
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--finish', choices=('glossy', 'matte'), default='matte')
    args = parser.parse_args(argv)
    if args.source.stat().st_size > 16*1024*1024:
        raise ValueError('Select default.xbe, not a disc or archive pack')
    result, receipt = apply(args.source.read_bytes(), finish=args.finish)
    # Exclusive binary creation also rejects aliases and existing outputs.
    with args.output.open('xb') as stream:
        try:
            stream.write(result)
        except BaseException:
            stream.close()
            args.output.unlink()
            raise
    verify(args.output.read_bytes(), finish=args.finish)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
