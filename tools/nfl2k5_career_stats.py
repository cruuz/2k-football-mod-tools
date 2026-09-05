#!/usr/bin/env python3
"""Inspect/export/import real career counters without changing a source or XBE.

Input: a bare disc ROST body or wrapped ROST resource. With --image, extract
outer entry 5 read-only and write a new bare body suitable for a build pass.
Runtime save inputs are deliberately refused: their container must be re-signed
through the separate save lane. No network fetch or name-only matching occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_career_stats as stats
from mod_editor.core import nfl2k5_roster_records as records


def _read(path: Path, limit: int) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_size > limit:
        raise stats.CareerStatsError(f'requires a regular non-symlink input <= {limit} bytes: {path}')
    with path.open('rb') as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise stats.CareerStatsError('input grew beyond the size limit')
    return data


def _load(path: Path, image: bool) -> tuple[bytes, bytes]:
    if image:
        with records._outer_image()(path) as archive:
            entry = records._entry(archive)
            resource = archive.read(entry.virtual_offset, entry.size)
        body = resource[records.RESOURCE_HEADER_SIZE:]
        stats.decode_body(body)
        return body, b''
    data = _read(path, records.RESOURCE_SIZE)
    header = b''
    if len(data) == records.RESOURCE_SIZE and data[:4] == b'ROST':
        header, data = data[:0x20], data[0x20:]
        if int.from_bytes(header[4:8], 'little') != len(data):
            raise stats.CareerStatsError('resource body length mismatch')
    stats.decode_body(data)
    return data, header


def _preflight_output(path: Path, sources: tuple[Path, ...]) -> None:
    if os.path.lexists(path):
        raise stats.CareerStatsError(f'output already exists: {path}')
    if any(path.resolve() == source.resolve() for source in sources):
        raise stats.CareerStatsError('output must not be a source')
    if not path.parent.is_dir():
        raise stats.CareerStatsError(f'output parent must already exist: {path.parent}')
    for parent in (path.parent, *path.parent.parents):
        if parent.is_symlink():
            raise stats.CareerStatsError(f'symlinked output parent refused: {parent}')


def _write_new(path: Path, data: bytes) -> None:
    with path.open('xb') as handle:
        handle.write(data)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('inspect', 'export', 'import'):
        p = sub.add_parser(command)
        p.add_argument('input', type=Path)
        p.add_argument('--image', action='store_true')
        p.add_argument('--base-year', type=int, default=2004,
                       help='current roster year, not a completed-history year (default 2004)')
        if command != 'inspect':
            p.add_argument('--output', type=Path, required=True)
        if command == 'import':
            p.add_argument('csv', type=Path)
            p.add_argument('--reserved-tail-words', type=int, default=0)
            p.add_argument('--receipt', type=Path)
    args = parser.parse_args(argv)
    try:
        body, header = _load(args.input, args.image)
        if args.command == 'inspect':
            print(json.dumps(stats.decode_body(body).summary(), indent=2))
            return 0
        sources = (args.input,) + ((args.csv,) if args.command == 'import' else ())
        _preflight_output(args.output, sources)
        if args.command == 'export':
            _write_new(args.output, stats.export_csv(body, base_year=args.base_year).encode('utf-8'))
            print(json.dumps({'output': str(args.output), 'schema': stats.SCHEMA, 'source_unchanged': True}))
            return 0
        if args.receipt:
            if args.receipt.resolve() == args.output.resolve():
                raise stats.CareerStatsError('receipt and binary output must be different files')
            _preflight_output(args.receipt, sources)
        csv_bytes = _read(args.csv, 32 * 1024 * 1024)
        rows = stats.read_csv(csv_bytes.decode('utf-8-sig'))
        result, receipt = stats.apply_body(body, rows, base_year=args.base_year,
                                          reserved_tail_words=args.reserved_tail_words)
        receipt.update({'csv_sha256': hashlib.sha256(csv_bytes).hexdigest(), 'output': str(args.output),
                        'source_unchanged': True, 'format': 'resource' if header else 'body'})
        encoded_receipt = (json.dumps(receipt, indent=2) + '\n').encode('utf-8')
        _write_new(args.output, header + result)
        if args.receipt:
            _write_new(args.receipt, encoded_receipt)
        print(json.dumps({k: v for k, v in receipt.items() if k != 'rows'}, indent=2))
        return 0
    except (stats.CareerStatsError, records.RosterRecordError, OSError, UnicodeError) as exc:
        print(f'CAREER_STATS_REFUSED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
