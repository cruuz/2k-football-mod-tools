#!/usr/bin/env python3
"""Build Team Select uniform cards from two verified sets of kit materials and an explicit league project.

The PNG masters retain the project's untouched RGBA pixels. The import PNGs retain the reviewed Xbox
card's untouched pixels and fit its 256-color format. The retained helmet silhouette protects both.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tools/b77')]
import u1_cards as U
import nfl_tset_png_import as palette_tools
from mod_editor.core import nfl2k5_menu_helmet_w2026 as slots
from nfl2k5_playbook_position_recode import OuterImage

SHADER = Path(__file__).with_name('u1_blender_bump.py')
CAMERA_INPUTS = {
    'jersey': (
        'torso',
        'sleeve',
        'digit_jersey_3',
        'digit_jersey_0',
        'digit_arm_3',
        'digit_arm_0',
        'bump_jersey',
        'bump_sleeve',
    ),
    'pants': ('pants', 'bump_pants'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rgba(path):
    with Image.open(path) as image:
        return np.array(image.convert('RGBA'), dtype=np.uint8)


def card_name(sel):
    if not re.fullmatch(r'\d\d[HA]\d+', sel):
        raise ValueError(f'Invalid kit selector {sel}')
    return f'unif_{sel[2].lower()}{sel[:2]}_{int(sel[3:])}_256'


def project_cards(project, asset_root):
    cards = {}
    for edit in json.loads(project.read_text(encoding='utf-8'))['edits']:
        if (edit.get('kind'), edit.get('family'), edit.get('resolution')) != ('team_select', 'unif', 256):
            continue
        side = {'home': 'H', 'away': 'A'}[edit['side']]
        key = f"{edit['asset_code']}{side}{int(edit['style'])}"
        if key in cards:
            raise ValueError(f'Duplicate Team Select uniform card {key}')
        path = (asset_root / edit['png']).resolve(strict=True)
        if not path.is_relative_to(asset_root) or not path.is_file():
            raise ValueError(f'{key} card leaves the supplied project assets: {path}')
        cards[key] = path
    return cards


def item(materials, phase, view, out, cache):
    file = {k: m[phase] for k,m in materials.items()}
    torso = cache / ('torso-'+materials['torso'][phase+'_rgba']+'.png')
    if not torso.is_file():
        U.torso_card(Path(file['torso']),torso)
    tex = {'UNIF_jersey':str(torso), 'UNIF_sleeve':file['sleeve'], 'UNIF_pants':file['pants']}
    for side, digit in (('L','3'),('R','0')):
        tex['NUMBER_'+side] = file['digit_jersey_'+digit]
        for shoulder in ('A','B'):
            tex[f'NUMBER_shoulder_{shoulder}_{side}'] = file['digit_arm_'+digit]
    hide = U.BODY_HIDE + U.HEAD_HIDE + ['NUMBER_M','NUMBER_shoulder_A_M','NUMBER_shoulder_B_M',
                                        'HI_HELMET*','HELMET_*','LOGO_*','FACEMASK*']
    return {'tex':tex,'hide':hide,'uv_scale':U.UV_SCALE,'shell':'C','facemask':'FACEMASK12',
            'bump':{k:file[v] for k,v in (('UNIF_jersey','bump_jersey'),('UNIF_sleeve','bump_sleeve'),('UNIF_pants','bump_pants'))},
            'views':[U.view(view,'H',out)]}


def render_layers(kits, models, out, batch_size, software=False):
    cache = out / 'work'
    cache.mkdir(parents=True, exist_ok=True)
    dependencies = [
        SHADER,
        Path(U.__file__),
        models / 'hi_body_o3c114.gltf',
        models / 'hi_body_o3c114.bin',
        models / 'hi_head_o3c115.gltf',
        models / 'hi_head_o3c115.bin',
    ]
    source_pins = {f.name: sha(f.read_bytes()) for f in dependencies}
    source_pins['material_binding'] = sha(inspect.getsource(item).encode())
    version = subprocess.check_output(['blender', '--version'], text=True).splitlines()[0]
    driver = subprocess.check_output(['glxinfo', '-B'], text=True)
    gpu = next((s.strip() for s in driver.splitlines() if s.startswith('OpenGL renderer string:')), '')
    if software:
        # R2-F (11/20): the only NVIDIA X server on the authoring machine is Noah's own display, which agents must not
        # use. --software-gl renders on a private X display with Mesa llvmpipe instead (measured against the nov20 GPU
        # renders of the same views: mean 0.23 and 0.14 levels per channel, p99 at most 4). The renderer string is part
        # of every cache key, so the old and new views of a run always come from the same renderer.
        if os.environ.get('DISPLAY', '') in ('', ':0', ':0.0') or 'llvmpipe' not in gpu:
            raise ValueError(f'--software-gl needs a private X display with Mesa llvmpipe, found {gpu}')
    elif 'NVIDIA' not in gpu:
        raise ValueError(f'Expected headless NVIDIA OpenGL, found {gpu}')
    context = json.dumps([version, gpu, source_pins], sort_keys=True)
    pending, layers = {}, {}
    checked = set()
    for sel, kit in kits.items():
        phases = layers[sel] = {}
        for phase in ('old', 'new'):
            phases[phase] = {}
            for material in kit['materials'].values():
                artifact = (material[phase], material[phase + '_file'])
                if artifact not in checked and sha(Path(artifact[0]).read_bytes()) != artifact[1]:
                    raise ValueError(f'{sel}: changed {phase} source {artifact[0]}')
                checked.add(artifact)
            for view, required in CAMERA_INPUTS.items():
                hashes = [kit['materials'][k][phase + '_rgba'] for k in required]
                key = sha(json.dumps([context, view, hashes]).encode())
                path = cache / (key + '.png')
                phases[phase][view] = path
                if key not in pending:
                    sealed = path.with_suffix('.ok')
                    if sealed.is_file():
                        if not path.is_file() or sha(path.read_bytes()) != sealed.read_text().strip():
                            raise ValueError(f'Cached garment render failed verification: {path}')
                    else:
                        pending[key] = item(kit['materials'], phase, view, path, cache)
    views = list(pending.items())
    if views:
        import fcntl  # The Linux authoring machine serializes access to its sole Blender GPU.

        subprocess.run(
            ['nvidia-smi', '--query-gpu=index,name,utilization.gpu,memory.used', '--format=csv'], check=True
        )
        with open('/tmp/b77-blender.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            # Headless EEVEE uses the host's NVIDIA OpenGL driver. No interactive Blender window is opened.
            env = dict(os.environ)
            if not software:
                env.pop('LIBGL_ALWAYS_SOFTWARE', None)
            for start in range(0, len(views), batch_size):
                batch = views[start : start + batch_size]
                name = 'batch-' + batch[0][0][:16]
                job = {
                    'head': str(models / 'hi_head_o3c115.gltf'),
                    'body': str(models / 'hi_body_o3c114.gltf'),
                    'arms_down': U.LAYOUT['arms_down'],
                    'morphs': U.LAYOUT['morphs'],
                    'items': [value for _, value in batch],
                }
                path = cache / (name + '.json')
                path.write_text(json.dumps(job))
                log = cache / (name + '.log')
                print(f'{start + 1}–{start + len(batch)} of {len(views)} unique garment renders', flush=True)
                with log.open('w') as stream:
                    subprocess.run(
                        [
                            'nice',
                            '-n',
                            '10',
                            'blender',
                            '-b',
                            '--factory-startup',
                            '-t',
                            '4',
                            '--python-exit-code',
                            '1',
                            '-P',
                            str(SHADER),
                            '--',
                            str(path),
                        ],
                        env=env,
                        check=True,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                    )
                for key, _ in batch:
                    f = cache / (key + '.png')
                    with Image.open(f) as im:
                        if im.size != (1024, 1024):
                            raise ValueError(f'Unexpected garment layer {f}: {im.size}')
                        im.verify()
                    f.with_suffix('.ok').write_text(sha(f.read_bytes()) + '\n')
    return layers, {
        'source_files': source_pins,
        'blender': version,
        'opengl': gpu,
        'new_views': len(views),
        'unique_views': len({p for k in layers.values() for phase in k.values() for p in phase.values()}),
        **({'software_gl': True} if software else {}),
    }


def garment(paths):
    with Image.open(paths['pants']) as pants, Image.open(paths['jersey']) as jersey:
        both = Image.alpha_composite(U.saturate(pants), U.saturate(jersey))
    return premul(np.asarray(U.box_reduce(both, 256)))


def premul(colors):
    result = colors.astype(np.float32)
    result[..., :3] *= result[..., 3:4] / 255.0
    return result


def protected_area(helmet_layers, sel):
    mask = np.zeros((256, 256), dtype=bool)
    pins = {}
    for step in ('old', 'new'):
        path = helmet_layers / step / (sel + '_unif.png')
        pins[step] = sha(path.read_bytes())
        with Image.open(path) as im:
            if im.size != (1024, 1024) or not im.getchannel('A').getbbox():
                raise ValueError(f'Invalid reviewed helmet layer {path}')
            samples = np.asarray(im.getchannel('A')) > 0
        # A single partially covered supersample freezes its whole native cell.
        mask |= samples.reshape(256, 4, 256, 4).any(axis=(1, 3))
    # The approved card may carry retouched edge pixels just outside the sampled shell and facemask.
    fringe = Image.fromarray(mask.astype(np.uint8)).filter(ImageFilter.MaxFilter(5))
    return np.asarray(fringe) != 0, pins


def native_palette(desired, original, mask):
    """Keep frozen colors and each native alpha. Spend available entries on the largest visible color errors."""
    output = original.copy()
    if not mask.any():
        return output
    fixed = np.unique(original[~mask].reshape(-1, 4), axis=0)
    targets, inverse, counts = np.unique(desired[mask], axis=0, return_inverse=True, return_counts=True)
    rgb = targets[:, :3].astype(np.int32)
    closest = np.empty_like(targets)
    distances = np.full(len(targets), 3 * 255**2 + 1, dtype=np.int32)

    def include(color):
        difference = rgb - color[:3].astype(np.int32)
        squared = (difference * difference).sum(axis=1)
        better = (targets[:, 3] == color[3]) & (squared < distances)
        distances[better] = squared[better]
        closest[better] = color

    for color in fixed:
        include(color)
    fixed_alphas = set(fixed[:, 3])
    used = len(fixed)
    for alpha in np.unique(targets[:, 3]):
        if alpha not in fixed_alphas:
            matches = np.flatnonzero(targets[:, 3] == alpha)
            include(targets[matches[np.argmax(counts[matches])]])
            used += 1

    # Gradients split a small mark across many nearby RGBs. Count the nearby shades together
    # and weight the visible (premultiplied) error, including antialiasing at the garment edge.
    bins = targets.copy()
    bins[:, :3] //= 8
    _, group = np.unique(bins, axis=0, return_inverse=True)
    group = group.reshape(-1)
    samples = np.bincount(group, weights=counts)[group]
    weights = (targets[:, 3].astype(np.float64) / 255.0) ** 2 * np.sqrt(samples)
    for _ in range(256 - used):
        scores = distances * weights
        candidate = int(np.argmax(scores))
        if scores[candidate] == 0:
            break
        include(targets[candidate])
    output[mask] = closest[inverse.reshape(-1)]
    return output


def garment_support(paths, shape):
    """Return native cells covered by the changed jersey or visible changed pants."""
    changed = {view for view in CAMERA_INPUTS if paths['old'][view] != paths['new'][view]}
    if not changed or len(changed) == len(CAMERA_INPUTS):
        return np.full(shape, bool(changed), dtype=bool)
    visible = np.zeros(shape, dtype=bool)
    for phase in ('old', 'new'):
        with Image.open(paths[phase]['jersey']) as shirt:
            jersey = np.asarray(shirt.getchannel('A'))
        if 'jersey' in changed:
            samples = jersey > 0
        else:
            with Image.open(paths[phase]['pants']) as image:
                pants = np.asarray(image.getchannel('A'))
            samples = (pants > 0) & (jersey < 255)
        h, w = shape
        visible |= samples.reshape(h, samples.shape[0] // h, w, samples.shape[1] // w).any(axis=(1, 3))
    return visible


def make_output(sel, paths, source, stored, protected):
    old, new = garment(paths['old']), garment(paths['new'])
    render_change = np.abs(new[..., :3] - old[..., :3]).max(axis=2) > 5
    # Some reviewed cards depict a different number, stripe or sleeve than the released uniform.
    # A changed garment takes its actual new render across its entire visible material, including flat
    # color interiors. A pixel difference stencil would splice the two designs across those interiors.
    support = garment_support(paths, protected.shape) if render_change.any() else np.zeros_like(protected)
    visible = (source[..., 3] > 0) & (old[..., 3] > 0) & (new[..., 3] > 0)
    edit = support & visible & ~protected
    master = source.copy()
    alpha = new[edit, 3:4] / 255.0
    master[edit, :3] = np.clip(np.floor(new[edit, :3] / alpha + 0.5), 0, 255).astype(np.uint8)
    desired = stored.copy()
    desired[edit, :3] = master[edit, :3]
    compiled = native_palette(desired, stored, edit)
    if not np.array_equal(master[~edit], source[~edit]) or not np.array_equal(compiled[~edit], stored[~edit]):
        raise ValueError(f'{sel} changed protected pixels')
    if not np.array_equal(master[..., 3], source[..., 3]) or not np.array_equal(
        compiled[..., 3], stored[..., 3]
    ):
        raise ValueError(f'{sel} changed card transparency')
    diff = np.any(compiled != stored, axis=2)
    return (
        master,
        compiled,
        dict(
            changed_pixels=int(diff.sum()),
            master_changed_pixels=int(np.any(master != source, axis=2).sum()),
            render_changed_pixels=int(render_change.sum()),
            candidate_cloth_pixels=int(edit.sum()),
            protected_pixels=int(protected.sum()),
            protected_source_changed=int(np.any(master[protected] != source[protected], axis=1).sum()),
            protected_native_changed=int(np.any(compiled[protected] != stored[protected], axis=1).sum()),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        'project',
        'inputs',
        'models',
        'helmet-layers',
        'reviewed-disc',
        'reviewed-card-receipt',
        'out',
    ):
        parser.add_argument('--' + key, type=lambda s: Path(s).resolve(), required=True)
    parser.add_argument('--asset-root', type=lambda s: Path(s).resolve())
    parser.add_argument('--kits', nargs='+')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--software-gl', action='store_true')
    args = parser.parse_args()
    asset_root = args.asset_root or args.project.parent
    if args.out.is_relative_to(asset_root) or args.batch_size < 1:
        raise ValueError('Choose an output outside the reviewed source and a positive batch size')
    cards = project_cards(args.project, asset_root)
    kits = json.loads(args.inputs.read_text())['kits']
    selected = sorted(set(args.kits or kits))
    if set(selected) - set(kits) or set(selected) - set(cards):
        raise ValueError('A selected kit lacks its verified materials or a reviewed project card')
    pins = json.loads(args.reviewed_card_receipt.read_text())
    baseline = {}
    with OuterImage(args.reviewed_disc, writable=False) as archive:
        for sel in selected:
            name = card_name(sel)
            pin = pins[name]
            source = rgba(cards[sel])
            source_sha = sha(source.tobytes())
            if source.shape != (256, 256, 4) or source_sha != pin['new_rgba_sha256']:
                raise ValueError(f'{sel}: the project image differs from the reviewed helmet art')
            _, span = slots.locate(archive, 'logos', name.removesuffix('_256'))
            indices, palette, _ = slots.read_slot(span)
            stored = palette[indices].astype(np.uint8)
            if sha(stored.tobytes()) != pin['stored_rgba_sha256']:
                raise ValueError(f'{sel}: reviewed physical slot differs')
            mask, masks = protected_area(args.helmet_layers, sel)
            baseline[sel] = source, stored, mask, masks
    args.out.mkdir(parents=True, exist_ok=True)
    layers, render = render_layers(
        {sel: kits[sel] for sel in selected}, args.models, args.out, args.batch_size, args.software_gl
    )
    files, masters = args.out / 'assets/files', args.out / 'masters'
    files.mkdir(parents=True, exist_ok=True)
    masters.mkdir(exist_ok=True)
    receipt = {
        'schema': 'nfl2k5_b81_uniform_cards/v1',
        'project': str(args.project),
        'project_sha256': sha(args.project.read_bytes()),
        'input_inventory_sha256': sha(args.inputs.read_bytes()),
        'render': render,
        'unchanged_kits': sorted(set(cards) - set(kits)),
        'cards': {},
    }
    for sel in selected:
        name = card_name(sel)
        source, stored, mask, masks = baseline[sel]
        master, imported, measurements = make_output(sel, layers[sel], source, stored, mask)
        file = 'b81unif_' + name + '.png'
        target = files / file
        if measurements['changed_pixels']:
            Image.fromarray(imported, 'RGBA').save(target)
            Image.fromarray(master, 'RGBA').save(masters / file)
            if not np.array_equal(rgba(target), imported):
                raise ValueError(f'{sel} import PNG changed on readback')
            level = palette_tools.MipLevel(0, 256, 256, imported.tobytes())
            p, ind, _ = palette_tools.quantize_levels([level])
            readback = palette_tools.rgba_from_indices(ind[0], p)
            if readback != imported.tobytes():
                raise ValueError(f'{sel} failed ordinary Studio palette readback')
        receipt['cards'][name] = dict(
            selector=sel,
            **measurements,
            file=file if measurements['changed_pixels'] else None,
            new_file_sha256=sha(target.read_bytes()) if measurements['changed_pixels'] else None,
            source_rgba_sha256=sha(source.tobytes()),
            source_file_sha256=sha(cards[sel].read_bytes()),
            source_native_sha256=sha(stored.tobytes()),
            master_rgba_sha256=sha(master.tobytes()),
            new_rgba_sha256=sha((imported if measurements['changed_pixels'] else source).tobytes()),
            stored_rgba_sha256=sha(imported.tobytes()),
            helmet_layers=masks,
        )
    destination = args.out / ('card_receipt.json' if not args.kits else 'pilot_receipt.json')
    destination.write_text(json.dumps(receipt, indent=1, sort_keys=True) + '\n')
    print(
        f"Wrote {destination}: {len(selected)} kits; {sum(r['changed_pixels'] > 0 for r in receipt['cards'].values())} changed import cards"
    )


if __name__ == '__main__':
    main()
