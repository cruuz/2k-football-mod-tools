#!/usr/bin/env python3
"""Pinned N07 native repair on one existing copy of the 2026-10-13 fixes disc.

--base and --retail are read only. --disc must be a distinct existing copy.
Writes only the Studio plan's fixed metadata/XBE spans and two appended archive
extents. Archive payloads and existing allocation addresses remain unchanged.
The complete input must hash as the base or the deterministically computed output.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_moment_coaches as coaches
from mod_editor.core import platform_compat as io

BASE_SHA256 = '520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4'
BASE_SIZE = 6004408320
BLOCK = 8 << 20


def require(ok, message):
    if not ok:
        raise ValueError(message)


def open_binary(path, writable=False):
    fd = os.open(path, (os.O_RDWR if writable else os.O_RDONLY) | getattr(os, 'O_BINARY', 0)
                 | getattr(os, 'O_NOFOLLOW', 0))
    return os.fdopen(fd, 'r+b' if writable else 'rb')


def digest(path):
    h = hashlib.sha256()
    with open_binary(path) as f:
        while b := f.read(BLOCK): h.update(b)
    return h.hexdigest()


def expected_blocks(base, writes):
    end = max([BASE_SIZE] + [at + len(raw) for at,raw in writes])
    with open_binary(base) as f:
        for lo in range(0, end, BLOCK):
            size = min(BLOCK, end-lo)
            buf = bytearray(f.read(size)).ljust(size, b'\0')
            for at,raw in writes:
                start, stop = max(lo, at), min(lo+size, at+len(raw))
                if start < stop: buf[start-lo:stop-lo] = raw[start-at:stop-at]
            yield lo, bytes(buf)


def run(args):
    require(args.base.resolve() != args.disc.resolve() and not os.path.samefile(args.base, args.disc),
            'disc must be a separate base copy')
    require(args.retail.resolve() != args.disc.resolve() and not os.path.samefile(args.retail, args.disc),
            'retail source is read only')
    require(args.base.stat().st_size == BASE_SIZE and digest(args.base) == BASE_SHA256, 'unknown complete base hash')
    writes, plan = coaches.image_plan(args.base, args.retail)
    h = hashlib.sha256()
    for _,block in expected_blocks(args.base, writes): h.update(block)
    expected = h.hexdigest()
    before = digest(args.disc)
    require(before in (BASE_SHA256, expected), 'unknown complete input disc hash')
    written = 0
    with open_binary(args.disc, writable=True) as f:
        for at, raw in writes:
            if io.pread(f.fileno(), len(raw), at) == raw: continue
            f.seek(at); require(f.write(raw) == len(raw), 'short write'); written += len(raw)
        f.flush(); os.fsync(f.fileno())
    # Equality to the Studio plan is checked for every output byte. This also
    # proves zero changes outside the listed spans, including original padding.
    with open_binary(args.disc) as f:
        for at, block in expected_blocks(args.base, writes):
            require(f.read(len(block)) == block, f'outside-scope or unequal output at {at:#x}')
        require(f.read(1) == b'', 'unexpected output tail')
    after = digest(args.disc)
    require(after == expected, 'output hash mismatch')
    replay, detail = coaches.image_plan(args.disc, args.retail)
    require(not replay, 'Studio replay writes bytes')
    receipts = {
        'write':dict(before_sha256=before, after_sha256=after, bytes_written=written,
                     output_size=args.disc.stat().st_size, plan=plan),
        'replay':dict(bytes_written=0, planned_spans=len(replay)),
        'scope':dict(base_sha256=BASE_SHA256, output_sha256=after, outside_scope_changed_bytes=0,
                     scope=plan['writes'], append_bytes=args.disc.stat().st_size-BASE_SIZE),
        'studio_equality':dict(equal=True, compared_bytes=args.disc.stat().st_size,
                               compiler='nfl2k5_moment_coaches.image_plan', output_sha256=after),
    }
    args.receipts.mkdir(parents=True, exist_ok=True)
    for name, doc in receipts.items():
        (args.receipts/(name+'.json')).write_text(json.dumps(doc,indent=2)+'\n',newline='\n')
    print(json.dumps({name:{k:v for k,v in doc.items() if k not in ('plan','scope')}
                      for name,doc in receipts.items()},indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','retail','disc','receipts'): p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
