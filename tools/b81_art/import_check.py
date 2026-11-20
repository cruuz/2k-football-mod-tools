"""Which rebuilt Standard-shell textures the Studio importer can take as new source art (the slot's stored size is
fixed): prints the names that do not fit."""
import sys, json; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C
sys.path[:0] = [str(C.WT), str(C.WT / 'tools')]
import b81_helmet_cleanup as hc
from pathlib import Path
DISC = Path(__import__('os').environ.get('B81_ART_DISC', '/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.9 (2026-11-05).xiso.iso'))
RI = Path(__import__('os').environ.get('NFL2K5_RETAIL_INDEX', '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))
names = sys.argv[1:]
kits = hc.read_kits(DISC, sorted({n.split('_')[1] for n in names}))
bad = []
for n in names:
    fam, sel = n.split('_')
    try: hc.imported(kits[sel], sel, fam, C.WORK.parent / 'out' / 'helmets_assigned' / f'{n}.png', RI)
    except Exception as e: bad.append(n); print('NO FIT', n, str(e)[:80], flush=True)
print('checked', len(names), 'do not fit:', bad); print('IMPORT_CHECK_DONE')
