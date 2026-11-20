#!/usr/bin/env python3
"""Ruling 2 (b81-retail-free-art): convert the kit-fix rows whose every fix is authored art or an erasure into
[clear by rule] + runs of the authored texels only (kitfix_convert.convert_row), in parallel, each checked texel for
texel and against its compile pin.   kitfix_families.py DISC FAMILY...   (rows of data/nfl2k5_kit_fixes_2026_b81u.json
whose defects all lie in the named families and that carry no clear yet)"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tools/b81_uniforms')]
from mod_editor.core import nfl2k5_bump_texture_writer as bw  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as kf  # noqa: E402
import kitfix_convert as kc  # noqa: E402


def sha(data):
    return hashlib.sha256(data).hexdigest()


ERASURE_FIRST = False


def job(args):
    disc, selector, rows = args
    with bw._Image.open(Path(disc), writable=False) as image:
        index = bw._parsed_index(image)
        e = {bw.logical_name_for(x.name_id): x for x in index.entries}[selector + '.IFF']
        raw = image.read_segments(index.sub_extents(e, 0, e.size))
    out = []
    for row in rows:
        c = kf._chunk_for(raw, row['chunk'])
        span = raw[c.offset:c.end_offset]
        assert sha(span) == row['before_sha256'], (selector, row['chunk'], 'input differs from its pin')
        ops, line = kc.convert_row(row, span, [], [], erasure_first=ERASURE_FIRST)
        new, _detail = kf.compile_texture(span, dict(row, ops=ops))
        assert sha(new) == row['after_sha256'], (selector, row['chunk'], 'compile differs from its output pin')
        out.append((row['chunk'], ops, line))
    return selector, out


def main():
    global ERASURE_FIRST
    disc, args = sys.argv[1], sys.argv[2:]
    if args and args[0] == '--erasure-first':
        ERASURE_FIRST, args = True, args[1:]
    source = None
    if args and args[0] == '--from':                    # rows as authored (runs), from an earlier copy of the document
        source, args = json.loads(Path(args[1]).read_text(encoding='utf-8')), args[2:]
    families = set(args)
    path = kf.DATA_B81U
    document = json.loads(path.read_text(encoding='utf-8'))
    pool_rows = (source or document)['textures']
    only = None
    if args and args[0] == '--rows':
        only, args = set(args[1].split(',')), args[2:]
        families = set(args)
    rows = [r for r in pool_rows if set(r['defects']) <= families and not any(op['op'] == 'clear' for op in r['ops'])
            and (only is None or f"{r['selector']}:{r['chunk']}" in only)]
    by = {}
    for r in rows:
        by.setdefault(r['selector'], []).append(r)
    done = {}
    with ProcessPoolExecutor(max_workers=3) as pool:
        for selector, out in pool.map(job, [(disc, s, rs) for s, rs in sorted(by.items())], chunksize=2):
            for chunk, ops, line in out:
                done[(selector, chunk)] = (ops, line)
    for r in document['textures']:
        if (r['selector'], r['chunk']) in done:
            r['ops'] = done[(r['selector'], r['chunk'])][0]
    path.write_text(json.dumps(document, sort_keys=True, separators=(', ', ': ')) + '\n', encoding='utf-8')
    kf.uniforms_b81()
    for (s, c), (_ops, line) in sorted(done.items()):
        print(f'{s}:{c}', json.dumps(line, sort_keys=True))
    print('converted', len(done), 'rows')


if __name__ == '__main__':
    main()
