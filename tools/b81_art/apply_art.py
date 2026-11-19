#!/usr/bin/env python3
"""b81-art: put the cleaned Team Select cards, mini helmets and the Carolina helmet assignment into an extracted
SOFTDRINK source folder (``nfl2k5_modpack.py extract PACK --out DIR --customize``).

  python3 apply_art.py --sources DIR --art ART_OUT [--dry-run]

ART_OUT holds ``assets/files/b81art_*.png``, ``card_receipt.json``, ``mini_receipt.json`` and ``new_helmet_art.json``
(this job's output folder). Every edit is checked first: the PNG the project names today must be the art the new one
was made from (RGBA SHA-256), or nothing is written. The new PNGs are copied beside the pack's own files and the
project's edits are repointed; nothing else in the project or the recipe changes. Writes ``b81art-apply-receipt.json``.
"""
import argparse, hashlib, json, shutil, sys
from pathlib import Path
import numpy as np
from PIL import Image

def rgba_sha(path):
    with Image.open(path) as im:
        return hashlib.sha256(np.ascontiguousarray(np.asarray(im.convert('RGBA'), dtype=np.uint8)).tobytes()).hexdigest()

def card_name(e):
    return f"{e['family']}_{'h' if e['side'] == 'home' else 'a'}{e['asset_code']}_{int(e['style'])}_{int(e['resolution'])}"

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--sources', required=True); ap.add_argument('--art', required=True); ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)
    src, art = Path(a.sources), Path(a.art)
    project_path = src / 'SOFTDRINK-league-project.json'
    project = json.loads(project_path.read_text(encoding='utf-8'))
    cards = json.loads((art / 'card_receipt.json').read_text())
    minis = json.loads((art / 'mini_receipt.json').read_text())
    reassign = json.loads((art / 'helmet_reassign.json').read_text())       # {slot selector: donor selector}
    new_helmets = json.loads((art / 'helmet_receipt.json').read_text()) if (art / 'helmet_receipt.json').is_file() else {}
    files = src / 'assets' / 'files'
    plan, problems = [], []
    helmets = {}
    for e in project['edits']:
        if e.get('kind') == 'live_helmet':
            helmets[(f"{e['asset_code']}{e['side']}{e['variant']}", e['family'])] = e
    for e in project['edits']:
        kind = e.get('kind')
        if kind == 'team_select':
            rec = cards.get(card_name(e))
            if rec and rec.get('file'):
                plan.append((e, 'png', art / 'assets' / 'files' / rec['file'], rec['source_rgba_sha256'], card_name(e)))
        elif kind == 'p8_texture' and e['asset_id'].split(':')[-1] in minis:
            rec = minis[e['asset_id'].split(':')[-1]]
            plan.append((e, 'png', art / 'assets' / 'files' / rec['file'], rec['source_rgba_sha256'], e['asset_id']))
        elif kind == 'live_helmet':
            sel = f"{e['asset_code']}{e['side']}{e['variant']}"
            if sel in reassign:
                donor = helmets[(reassign[sel], e['family'])]
                plan.append((e, 'png', Path(donor['png']), None, f"{e['family']}_{sel} <- {reassign[sel]}"))
            elif f"{e['family']}_{sel}" in new_helmets:
                rec = new_helmets[f"{e['family']}_{sel}"]       # a rebuilt logo: the slot's source art is replaced
                plan.append((e, 'png', art / 'assets' / 'files' / rec['file'], rec['source_rgba_sha256'], f"{e['family']}_{sel}"))
    expected = sum(1 for r in cards.values() if r.get('file')) + len(minis) + 2 * len(reassign) + len(new_helmets)
    if len(plan) != expected:
        problems.append(f'{len(plan)} edits matched, {expected} expected')
    for e, key, new, want, label in plan:
        if want is not None and rgba_sha(e[key]) != want:
            problems.append(f'{label}: the project PNG is not the art this card was made from')
        if not Path(new).is_file():
            problems.append(f'{label}: {new} is missing')
    if problems:
        print('\n'.join(problems)); return 1
    done = []
    # helmet reassignments read the donors' current paths, so resolve every new path before the first write
    resolved = []
    for e, key, new, want, label in plan:
        target = Path(new) if want is None else files / Path(new).name
        resolved.append((e, key, Path(new), target, label, want))
    for e, key, new, target, label, want in resolved:
        if not a.dry_run and want is not None:
            shutil.copyfile(new, target)
        done.append(dict(edit=label, before=str(e[key]), after=str(target)))
        e[key] = str(target)
    if not a.dry_run:
        project_path.write_text(json.dumps(project, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
        (src / 'b81art-apply-receipt.json').write_text(json.dumps(dict(edits_repointed=len(done), edits=done), indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(edits_repointed=len(done), cards=sum(1 for d in done if 'helm_' in d['edit'] or 'unif_' in d['edit']), dry_run=a.dry_run)))
    return 0

if __name__ == '__main__':
    sys.exit(main())
