import sys, json, hashlib; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, final
from pathlib import Path
from PIL import Image
def missing():
    kits = sorted({n.split('_')[1][1:] + n.split('_')[1][0].upper() + n.split('_')[2] for n in C.index()})
    have = {n.split('_')[1] for n in C.hindex()}
    return [k for k in kits if k not in have]
if __name__ == '__main__':
    from mod_editor.core import nfl2k5_kit_fixes_2026 as kf
    bump = kf.bump
    miss = missing(); print(miss)
    meta = json.load(open(final.OUT / 'meta.json'))
    with bump._Image.open(Path(final.DISC), writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        for sel in miss:
            entries = by_name.get(sel + '.IFF', [])
            assert len(entries) == 1, (sel, len(entries))
            raw = image.read_segments(index.sub_extents(entries[0], 0, entries[0].size))
            for fam, ci in (('helmet00', 11), ('helmet02', 12)):
                chunk = kf._chunk_for(raw, ci); span = raw[chunk.offset:chunk.end_offset]
                ch, decoded, textures = kf.native_textures(span, 'txtr')
                assert textures[0]['name'] == fam
                planes = kf.read_planes(decoded, ch, textures[0]); pal = kf.read_palette(decoded, ch, textures[0])
                rgba = pal[planes[0]].astype(np.uint8)
                name = f'{fam}_{sel}'
                Image.fromarray(rgba, 'RGBA').save(final.OUT / 'helmets' / (name + '.png'))
                meta['helmets'][name] = dict(span_sha256=hashlib.sha256(span).hexdigest(), rgba_sha256=hashlib.sha256(rgba.tobytes()).hexdigest(),
                                             resource_size=len(raw), offset=chunk.offset, length=len(span), mips=textures[0]['mips'], extra=True)
    json.dump(meta, open(final.OUT / 'meta.json', 'w'), indent=1, sort_keys=True)
    json.dump(miss, open(C.WORK / 'extra_kits.json', 'w'))
