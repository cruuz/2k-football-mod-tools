#!/usr/bin/env python3
"""Compile every catalogued retail target at 2x, one resource at a time.

Diagnostic artwork is generated in memory and never described as a finished
art pack. Only metadata receipts are written. No disc or pack copies exist.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_hires_texture as texture
from mod_editor.core import nfl2k5_hires_pack as pack
from mod_editor.core import nfl2k5_hires_budget as budget
from mod_editor.core import nfl2k5_music_archive as archive


@lru_cache(maxsize=8)
def artwork(width, height, mud=False):
    return b''.join(bytes((255 if (x//8)%2 else 0, 128 if (y//8)%2 else 0,
                          32 if mud else 224, 0 if (x//8+y//8)%4 == 0 else 255))
                    for y in range(height) for x in range(width))


def audit(image, *, progress=None):
    progress = progress or (lambda *_: None)
    start = time.monotonic()
    rows, budget_rows = [], []
    groups = {}
    for asset in texture.ASSETS:
        groups.setdefault(asset.outer, []).append(asset)
    with archive.Disc(image, descriptors=()) as disc:
        consumers = pack._consumer_check(disc, tuple(texture.BY_KEY))
        for outer, assets in sorted(groups.items()):
            entry = disc.archive_entries[outer]
            archive.require(entry.size <= 32*archive.BLOCK, 'Oversized outer')
            wanted = {a.chunk: a for a in assets}
            for chunk, _, raw in archive.chunks(disc.read_entry_range(entry, 0, entry.size)):
                if chunk not in wanted:
                    continue
                a = wanted[chunk]
                archive.require(entry.name_id == a.name_id and texture.sha(raw) == a.retail_sha256, 'Retail resource pin differs')
                before, base = texture.inspect_span(raw, a)
                rgba = artwork(a.native*2, a.height*2)
                if a.kind == 'TSET':
                    rgba = (rgba, artwork(a.native*2, a.height*2, True))
                output, compiled = texture.compile_texture(base, rgba, a, 2)
                after, restored_base = texture.inspect_span(output, a)
                archive.require(base == restored_base, 'Baseline restoration differs')
                archive.require(after == compiled['decoded'], 'Independent output inspection differs')
                budget_rows.append(dict(key=a.key, after=after))
                rows.append(dict(key=a.key, outer=outer, chunk=chunk, kind=a.kind, family=pack.asset_family(a),
                                 before=before, compiler=compiled))
                progress(len(rows), len(texture.ASSETS), a.key)
    archive.require(len(rows) == len(texture.ASSETS), 'Incomplete compilation census')
    memory = budget.model(texture.ASSETS, rows=budget_rows)
    budget.enforce(memory)
    return dict(schema='nfl2k5_hires_compile_all/v2', experimental=True, runtime_witnessed=False,
                artwork='in-memory diagnostic blocks; clean and mud have independent authored colors',
                assets=rows, memory=memory, consumer_xbe=consumers,
                largest_subset_within_model_ceiling=budget.family_subsets(texture.ASSETS),
                elapsed_seconds=time.monotonic()-start, disc_copies_created=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args(argv)
    def progress(done, total, key):
        if done % 50 == 0 or done == total:
            print(f'{done}/{total}: {key}', flush=True)
    result = audit(args.image, progress=progress)
    args.receipt.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(f"PASS: {len(result['assets'])} targets; {result['elapsed_seconds']:.3f} seconds; memory fit unproved")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
