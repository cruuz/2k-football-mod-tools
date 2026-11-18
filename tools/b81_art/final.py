"""Final (built-disc) Team Select cards and in-game helmets, decoded from the released v0.9 disc image (read only)."""
import sys, json, hashlib
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C
DISC = Path(__import__('os').environ.get('B81_ART_DISC', '/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.9 (2026-11-05).xiso.iso'))
OUT = C.WORK / 'final'
def dump_all(disc=DISC, out=OUT):
    from mod_editor.core import nfl2k5_kit_fixes_2026 as kf, nfl2k5_menu_helmet_w2026 as w, nfl2k5_historic_styles as hs
    from tools.nfl2k5_playbook_position_recode import OuterImage
    from tools import nfl_txtr as tx
    bump = kf.bump
    meta = {'cards': {}, 'helmets': {}}
    (out / 'cards').mkdir(parents=True, exist_ok=True); (out / 'helmets').mkdir(parents=True, exist_ok=True)
    with OuterImage(Path(disc), writable=False) as archive:
        for name in sorted(C.index()):
            fam, code, side, style, res = C.parse(name)
            member = f"{fam}_{'h' if side == 'home' else 'a'}{code}_{style}"
            agg = 'logos' if res == 256 else 'logos128'
            at, span = w.locate(archive, agg, member)
            indices, palette, base = w.read_slot(span)
            rgba = palette[indices].astype(np.uint8)
            Image.fromarray(rgba, 'RGBA').save(out / 'cards' / (name + '.png'))
            meta['cards'][name] = dict(span_sha256=hashlib.sha256(span).hexdigest(), rgba_sha256=hashlib.sha256(rgba.tobytes()).hexdigest())
    with bump._Image.open(Path(disc), writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        for name in sorted(C.hindex()):
            fam, rest = name.split('_'); sel = rest
            entries = by_name.get(sel + '.IFF', [])
            assert len(entries) == 1, (sel, len(entries))
            raw = image.read_segments(index.sub_extents(entries[0], 0, entries[0].size))
            chunk = kf._chunk_for(raw, 11 if fam == 'helmet00' else 12)
            span = raw[chunk.offset:chunk.end_offset]
            ch, decoded, textures = kf.native_textures(span, 'txtr')
            assert textures[0]['name'] == fam, textures[0]['name']
            planes = kf.read_planes(decoded, ch, textures[0])
            pal = kf.read_palette(decoded, ch, textures[0])
            rgba = pal[planes[0]].astype(np.uint8)
            Image.fromarray(rgba, 'RGBA').save(out / 'helmets' / (name + '.png'))
            meta['helmets'][name] = dict(span_sha256=hashlib.sha256(span).hexdigest(), rgba_sha256=hashlib.sha256(rgba.tobytes()).hexdigest(),
                                         resource_size=len(raw), offset=chunk.offset, length=len(span), mips=textures[0]['mips'],
                                         palette_used=int(len(np.unique(np.concatenate([p.ravel() for p in planes])))))
    json.dump(meta, open(out / 'meta.json', 'w'), indent=1, sort_keys=True)
    return meta
def card(name): return C.load(OUT / 'cards' / (name + '.png'))
def helmet(name): return C.load(OUT / 'helmets' / (name + '.png'))
if __name__ == '__main__':
    import time; t = time.time()
    m = dump_all()
    print(len(m['cards']), len(m['helmets']), round(time.time() - t))
