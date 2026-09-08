"""Transactional paired executable/ROST growth using the shipped archive writer.

EXPERIMENTAL / UNWITNESSED. All disc and pack access is bounded and streamed.
The destination is published only after both resources and every neighbor have
been independently reopened and verified. Source images are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from . import nfl2k5_music_archive as archive
from . import nfl2k5_music_banks as transport
from . import nfl2k5_roster_arena as arena
from . import nfl2k5_roster_arena_growth as growth
from . import platform_compat as io

ROST_INDEX = 5
ROST_NAME_ID = 1245141021


def _prepare(source, reserves_16, created_teams_extra):
    before = archive.identity(source)
    with archive.Disc(source, descriptors=()) as disc:
        archive.require(len(disc.archive_entries) > ROST_INDEX, 'missing main ROST resource')
        entry = disc.archive_entries[ROST_INDEX]
        archive.require(entry.name_id == ROST_NAME_ID and entry.size <= 1024*1024, 'foreign main ROST entry')
        original = disc.read_entry_range(entry, 0, entry.size)
        rost, migration = arena.migrate(original, reserves_16=reserves_16, created_teams_extra=created_teams_extra)
        executable = disc.entries.get('default.xbe')
        archive.require(executable is not None and executable.size <= 16*1024*1024, 'missing/oversized default.xbe')
        xbe, patch = growth.apply(disc.read(executable.size, executable.byte_offset),
                                  reserves_16=reserves_16, created_teams_extra=created_teams_extra)
        geometry = archive.layout(disc, {ROST_INDEX: len(rost)})
        final_size = (archive.align_up(geometry['image_size']) + len(xbe)
                      if len(xbe) > executable.size else geometry['image_size'])
        receipt = {'schema': 'nfl2k5_roster_arena_image/v1', 'experimental': True, 'runtime_witnessed': False,
                   'source_sha256': archive.digest(disc.read, disc.image_size), 'source_size': disc.image_size,
                   'output_size': final_size, 'rost': migration, 'xbe': patch,
                   'rost_sha256': hashlib.sha256(rost).hexdigest(),
                   'xbe_sha256': hashlib.sha256(xbe).hexdigest(), 'layout': geometry}
    archive.require(archive.identity(source) == before, 'source changed during arena planning')
    return rost, xbe, geometry, receipt


def plan(source, *, reserves_16=True, created_teams_extra=0):
    return _prepare(Path(source).resolve(), reserves_16, created_teams_extra)[3]


def image_status(path):
    """Pair status from fresh bounded extents; never infer a disc from XBE alone."""
    try:
        from .nfl2k5_save_rost import decode
        with archive.Disc(path, descriptors=()) as disc:
            entry = disc.archive_entries[ROST_INDEX]
            archive.require(entry.name_id == ROST_NAME_ID and entry.size <= 1024*1024, 'foreign ROST')
            doc = decode(disc.read_entry_range(entry, 0, entry.size))
            executable = disc.entries['default.xbe']
            archive.require(executable.size <= 16*1024*1024, 'oversized executable')
            settings = growth.read_settings(disc.read(executable.size, executable.byte_offset))
        if doc.overflow is None:
            return 'retail' if settings['status'] == 'retail' else 'foreign'
        return 'applied' if settings == dict(status='applied', reserves_16=doc.overflow.reserves_enabled,
                                             created_teams_extra=doc.overflow.extra_teams) else 'foreign'
    except (ValueError, OSError, IndexError, KeyError):
        return 'foreign'


def _verify(source, output, rost, xbe, geometry, receipt):
    with archive.Disc(source, descriptors=()) as old, archive.Disc(output, descriptors=()) as new:
        archive.require(new.image_size == receipt['output_size'], 'paired image size differs')
        archive.require(len(new.archive_entries) == len(geometry['entries']), 'outer count changed')
        for entry, projected in zip(new.archive_entries, geometry['entries']):
            archive.require((entry.name_id, entry.virtual_offset, entry.size) ==
                            (projected['name_id'], projected['offset'], projected['size']), 'outer framing differs')
            expected = receipt['rost_sha256'] if entry.table_index == ROST_INDEX else old.outer_hash(entry.table_index)
            archive.require(new.outer_hash(entry.table_index) == expected, f'outer {entry.table_index} hash differs')
        executable = new.entries['default.xbe']
        actual = new.read(executable.size, executable.byte_offset)
        archive.require(actual == xbe and growth.status(actual) == 'applied', 'paired executable read-back differs')
        entry = new.archive_entries[ROST_INDEX]
        archive.require(new.read_entry_range(entry, 0, entry.size) == rost, 'ROST read-back differs')
        archive.require(set(old.entries) == set(new.entries), 'named file set changed')
        unrelated = 0
        for name, entry in old.entries.items():
            if name == 'default.xbe' or name.startswith('vc_53450030/') or entry.attributes & 0x10:
                continue
            other = new.entries[name]
            archive.require((entry.size, entry.byte_offset) == (other.size, other.byte_offset), 'unrelated extent changed')
            archive.require(archive.digest(lambda n, at: old.read(n, entry.byte_offset+at), entry.size) ==
                            archive.digest(lambda n, at: new.read(n, other.byte_offset+at), other.size), 'unrelated file changed')
            unrelated += 1
        return {'status': 'verified', 'unchanged_outers': len(new.archive_entries)-1,
                'unchanged_named_files': unrelated, 'rost_sha256': receipt['rost_sha256'],
                'xbe_sha256': receipt['xbe_sha256'], 'output_sha256': archive.digest(new.read, new.image_size)}


def build_image(source, output, *, reserves_16=True, created_teams_extra=0, overwrite=False, progress=None):
    source = Path(source).resolve()
    rost, xbe, geometry, receipt = _prepare(source, reserves_16, created_teams_extra)
    progress = progress or (lambda *_: None)
    def build(_directory, staged):
        with archive.Disc(source, descriptors=()) as disc:
            archive.require(archive.layout(disc, {ROST_INDEX: len(rost)}) == geometry, 'source geometry changed')
            fd = os.open(staged, os.O_RDWR | getattr(os, 'O_BINARY', 0))
            try:
                transport._write_archive(fd, disc, geometry, {ROST_INDEX: rost}, {}, progress)
                named = archive.write_named(fd, lambda n, at: io.pread(fd, n, at), disc.partition,
                                            'default.xbe', lambda n, at: xbe[at:at+n], len(xbe))
                os.fsync(fd)
                return named
            finally:
                os.close(fd)
    named, checked = archive.transactional_copy(source, output, source_sha256=receipt['source_sha256'],
        scratch_bytes=receipt['output_size'] + 64*archive.BLOCK, build=build,
        verify=lambda staged, _: _verify(source, staged, rost, xbe, geometry, receipt),
        overwrite=overwrite, progress=progress)
    return {**receipt, 'verification': checked, 'executable_extent': named,
            'source_unchanged_verified': True, 'output': str(Path(output).resolve())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('plan', 'build'))
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--created-teams-extra', type=int, choices=(0, 2), default=0)
    parser.add_argument('--reserves-16', action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)
    try:
        kwargs = dict(reserves_16=args.reserves_16, created_teams_extra=args.created_teams_extra)
        if args.command == 'plan':
            result = plan(args.source, **kwargs)
        else:
            if args.output is None:
                parser.error('build requires --output')
            result = build_image(args.source, args.output, **kwargs)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, f'arena growth refused: {exc}\n')


if __name__ == '__main__':
    main()
