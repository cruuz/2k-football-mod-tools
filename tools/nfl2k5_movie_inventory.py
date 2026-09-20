#!/usr/bin/env python3
"""Read-only, bounded retail movie inventory. No emulator or movie extraction."""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.nfl_outer import parse_archive, read_entry_range
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_music_archive import Disc, digest
from mod_editor.core.nfl2k5_crib_reclaim import MOVIES as CRIB_MOVIES

BOOT_NAMES = ('espn_videogames.mov', 'vc.mov', 'espn_game_sound.mov', 'intro.mov')
NAMES = (*BOOT_NAMES, 'all_games.mov', *(r[1] for r in CRIB_MOVIES),
         'tips_defense.mov', 'tips_offense.mov')


def inventory(extracted, iso):
    tree = Path(extracted)
    archive = parse_archive(tree / 'vc_53450030' / '0')
    image = XbeImage((tree / 'default.xbe').read_bytes())
    ids = {zlib.crc32(n.upper().encode('utf-16le')): n for n in NAMES}
    heads = Counter(e.head_hex for e in archive.entries)
    streams = [e for e in archive.entries if e.head_hex == '000001ba']
    if len(streams) != 30 or {e.name_id for e in streams} != set(ids):
        raise ValueError('Retail movie inventory differs: do not infer eligible cuts')
    result = dict(schema='nfl2k5_movie_inventory/v1', runtime_witnessed=False,
                  xbe_sha256=image.sha256, outer_count=len(archive.entries),
                  outer_head_counts=dict(heads), movies=[], named_files=[])
    with Disc(iso, descriptors=()) as disc:
        result['source_bytes'] = disc.image_size
        result['partition_offset'] = disc.partition
        for name, e in disc.entries.items():
            result['named_files'].append(dict(name=name, size=e.size, byte_offset=e.byte_offset,
                                              sector=e.sector, directory=bool(e.attributes & 16)))
        for e in streams:
            name = ids[e.name_id]
            sample = read_entry_range(archive, e, 0, min(e.size, 1024**2))
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                'format=format_name:stream=codec_name,codec_type,width,height,sample_rate,channels',
                '-of', 'json', '-i', 'pipe:0'], input=sample, capture_output=True, check=True)
            metadata = json.loads(probe.stdout)
            direct = disc.archive_entries[e.table_index]
            if (direct.name_id, direct.size) != (e.name_id, e.size):
                raise ValueError('Extracted index and ISO differ')
            sha = digest(lambda n, at: read_entry_range(archive, e, at, n), e.size)
            if sha != disc.outer_hash(e.table_index):
                raise ValueError('Extracted movie and ISO differ')
            group = 'boot/publisher' if name in BOOT_NAMES else (
                'Crib reel' if name.startswith('crib_') else 'menu promotion/tutorial')
            calls = [0x74bce] if name in BOOT_NAMES else ([0x272a94] if group == 'Crib reel' else
                [{'tips_offense.mov': 0x3634be, 'tips_defense.mov': 0x3634de,
                  'all_games.mov': 0x363501}[name]])
            row = dict(name=name, category=group, outer=e.table_index, name_id=f'0x{e.name_id:08x}',
                size=e.size, sha256=sha, container='MPEG-PS / CRI Sofdec', probe=metadata,
                virtual_offset=e.virtual_offset, pack_segments=[asdict(s) for s in e.segments],
                iso_segments=[asdict(s) for s in disc.entry_spans(direct, 0, e.size)],
                call_sites=[f'0x{v:x}' for v in calls],
                hypothetical_payload_reclaim=e.size-2048,
                selected_by_trim_intro=name in BOOT_NAMES)
            result['movies'].append(row)
    # Enumerate absolute and near-call users of both movie APIs, across all file-backed sections.
    result['api_references'] = {}
    for target in (0x178150, 0x3cbbf0):
        calls, absolute = [], []
        for s in image.sections:
            raw = image.read(s.start, s.raw_size)
            for at in range(len(raw)-4):
                if raw[at] == 0xe8 and (s.start+at+5+int.from_bytes(raw[at+1:at+5], 'little', signed=True)) & 0xffffffff == target:
                    calls.append(hex(s.start+at))
            absolute.extend(hex(s.start+m.start()) for m in re.finditer(re.escape(target.to_bytes(4,'little')), raw))
        result['api_references'][hex(target)] = dict(near_calls=calls, absolute=absolute)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('extracted', type=Path, help='Folder containing default.xbe and vc_53450030')
    p.add_argument('iso', type=Path)
    p.add_argument('--json', type=Path, required=True)
    a = p.parse_args()
    if a.json.resolve().is_relative_to(a.extracted.resolve()) or a.json.resolve() == a.iso.resolve():
        p.error('Report must not overwrite retail inputs')
    report = inventory(a.extracted, a.iso)
    a.json.write_bytes((json.dumps(report, indent=2)+'\n').encode())
    print(f"Verified {len(report['movies'])} movie streams against extracted tree and ISO")

if __name__ == '__main__':
    main()
