#!/usr/bin/env python3
"""b81-art: check a built disc image against this job's pins (read only).
  1. every row of the helmet document is `after` on the disc;
  2. every Team Select card and changed mini on the disc decodes to the picture the Studio's compile makes of the new PNG;
  3. Carolina: style 0 home and away hold the same helmet pixels; the blue alternate holds the black 2012 helmet.
Usage: verify_build.py DISC.iso [--with-uniforms]  (run from the repository root)"""
import argparse, sys, json, hashlib
from pathlib import Path
import numpy as np
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C
sys.path.insert(0, str(C.WT / 'tools'))
import b81_helmet_cleanup as hc
from mod_editor.core import nfl2k5_menu_helmet_w2026 as w, nfl2k5_kit_fixes_2026 as kf
from tools.nfl2k5_playbook_position_recode import OuterImage
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('disc', type=Path)
p.add_argument('--with-uniforms', action='store_true', help='check the subsequent approved 128 MB uniform-card pins')
args = p.parse_args()
disc = args.disc; O = C.WORK.parent / 'out'
def sha(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
out = {}
st = hc.states(disc); out['helmet_rows'] = {k: st[k] for k in ('before', 'after', 'other', 'absent')}; out['helmet_rows_not_done'] = st['rows'][:20]
cards = json.load(open(O / 'card_receipt.json')); minis = json.load(open(O / 'mini_receipt.json'))
if args.with_uniforms:
    from tools.b81_uniforms.apply_cards import load_pins
    successors = load_pins()
    for name, pin in successors.items():
        if cards[name]['stored_rgba_sha256'] != pin['source_native_sha256']:
            raise ValueError(f'{name}: the uniform card does not follow this reviewed helmet card')
        cards[name] = dict(cards[name], stored_rgba_sha256=pin['stored_rgba_sha256'])
    out['uniform_cards_checked'] = len(successors)
bad = []; n = 0
with OuterImage(disc, writable=False) as archive:
    for name, rec in sorted(cards.items()):
        fam, code, side, style, res = C.parse(name)
        at, span = w.locate(archive, 'logos' if res == 256 else 'logos128', f"{fam}_{'h' if side == 'home' else 'a'}{code}_{style}")
        idx, pal, base = w.read_slot(span); n += 1
        if sha(pal[idx].astype(np.uint8)) != rec['stored_rgba_sha256']: bad.append(name)
    for name, rec in sorted(minis.items()):
        at, span = w.locate(archive, 'mini', name); idx, pal, base = w.read_slot(span); n += 1
        if sha(pal[idx].astype(np.uint8)) != rec['stored_rgba_sha256']: bad.append(name)
out['pictures_checked'] = n; out['pictures_not_as_pinned'] = bad
kits = hc.read_kits(disc, ['04H0', '04A0', '04H2', '04A2'])
def lvl(sel, fam):
    raw = kits[sel]; ch = kf._chunk_for(raw, hc.CHUNKS[fam]); return hc.level0(raw[ch.offset:ch.end_offset])[0]
out['carolina'] = {fam: dict(home_equals_away=bool((lvl('04H0', fam) == lvl('04A0', fam)).all()),
                             alt_home_equals_alt_away=bool((lvl('04H2', fam) == lvl('04A2', fam)).all()),
                             alt_differs_from_default=bool((lvl('04H2', fam) != lvl('04H0', fam)).any())) for fam in ('helmet00', 'helmet02')}
hrec = json.load(open(O / 'helmet_receipt.json')) if (O / 'helmet_receipt.json').is_file() else {}
kits.update(hc.read_kits(disc, sorted({n.split('_')[1] for n in hrec} - set(kits))))
out['new_helmets_checked'] = len(hrec)
out['new_helmets_not_as_built'] = [n for n in sorted(hrec) if not (lvl(n.split('_')[1], n.split('_')[0]) == C.load(O / 'helmets_compiled' / f'{n}.png')).all()]
ok = not out['new_helmets_not_as_built'] and out['helmet_rows']['other'] == 0 and out['helmet_rows']['before'] == 0 and out['helmet_rows']['absent'] == 0 and not bad \
     and all(v['home_equals_away'] and v['alt_home_equals_alt_away'] and v['alt_differs_from_default'] for v in out['carolina'].values())
out['ok'] = ok
print(json.dumps(out, indent=1))
sys.exit(0 if ok else 1)
