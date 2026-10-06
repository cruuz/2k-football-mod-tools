#!/usr/bin/env python3
"""Repair forward-pass rulings in an extracted XBE, preserving d2 and other owners.

Default inputs are exact v0.4 and d2 outputs or their exact repaired variants.
An independently stacked input requires its explicit SHA256. Complete native
classifier, text digest and allocator guards still apply. Outputs must be new.
Authored route repairs are separate scoped PLAY-resource operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.b765.d2_repair import V04_SHA256, COMBINED_SHA256
from mod_editor.core import nfl2k5_throw_tuning as tuning
from mod_editor.core import nfl2k5_xbe_space as space

V04_FIXED_SHA256 = 'af3a89167d40bca754a71476d60a861ed1876b486ad3d72e8eceb6c2bda15a2e'
D2_FIXED_SHA256 = '47dd860dfff98b03feed315b3be6fb6960784105fe450d35ef475b174b4307f2'


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def repair_xbe(payload):
    if space.status(payload) != 'applied':
        raise ValueError('Expected a sealed SOFTDRINK allocator')
    layout = space.layout(payload)
    result, component = tuning.apply_forward_pass_ruling(payload)
    if space.status(result) != 'applied' or space.layout(result) != layout:
        raise ValueError('Allocator changed during forward-pass repair')
    return result, dict(schema='b765.d2b.xbe-repair.v1', disc_file='default.xbe',
                        before_sha256=sha(payload), after_sha256=sha(result),
                        size=len(result), changed_bytes=component['changed_bytes'],
                        status='already_applied' if component['already_applied'] else 'applied',
                        scopes=component['edits'], component=component,
                        outside_scope_identical=True,
                        outside_scope_sha256=component['outside_scope_sha256'],
                        allocator_requests_unchanged=True, gameplay_witness=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--expected-input-sha256')
    args = parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        parser.error('Source must be a regular non-symlink XBE')
    for path in (args.output, args.receipt):
        if path.exists() or path.is_symlink():
            parser.error('Output and receipt must be new paths')
    if args.output.absolute() == args.receipt.absolute():
        parser.error('Output and receipt must differ')
    with args.source.open('rb') as stream:
        payload = stream.read(16 * 1024 * 1024 + 1)
    known = {V04_SHA256, COMBINED_SHA256, V04_FIXED_SHA256, D2_FIXED_SHA256}
    accepted = {args.expected_input_sha256} if args.expected_input_sha256 else known
    if sha(payload) not in accepted:
        parser.error('Unexpected input SHA256; no files written')
    result, receipt = repair_xbe(payload)
    receipt.update(source=str(args.source.absolute()), output=str(args.output.absolute()))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(args.output, flags, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(result)
    with args.receipt.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: receipt[k] for k in ('status', 'before_sha256', 'after_sha256', 'changed_bytes')}))


if __name__ == '__main__':
    main()
