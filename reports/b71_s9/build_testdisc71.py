"""Prepare/build the beta 71.1 down-label candidate and preserve every patch archive."""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['NFL2K5_RETAIL_INDEX'] = '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
from mod_editor.core import mod_build as mb, modpack, modpack_ops
from mod_editor.core import nfl2k5_modern_color as color
from mod_editor.core import nfl2k5_scorebug_ingame as scorebug
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
from mod_editor.core import nfl2k5_scorebug_sprite as resources
from mod_editor.core import nfl2k5_widescreen as widescreen
from mod_editor.core import nfl2k5_modern_arrowhead as arrowhead

BASE = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
OUT = Path('/home/noah/2K5 Mod Studio Builds')
NAME = 'NFL 2K5 MOD TEST 2026-09-16p (down label fix)'
EVIDENCE = ROOT / 'reports' / 'b71_s9' / 'build-receipt'
OPTIONS = ('scorebug', 'scorebug_runtime', 'modern_color', 'modern_arrowhead', 'widescreen')


def save(name, value):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')


def plan_for_disc():
    disc = OUT / (NAME + '.xiso.iso')
    plan = mb.apply_preset(mb.BuildPlan(source=str(BASE), target=str(disc)), 'softdrink_advanced')
    return dataclasses.replace(plan, scorebug=True, scorebug_runtime=True, modern_color=True, modern_arrowhead=True, widescreen=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    plan = plan_for_disc()
    snapshot = dict(preset='softdrink_advanced', options={key: getattr(plan, key) for key in OPTIONS},
                    source=plan.source, target=plan.target, scorebug_version=resources.VERSION,
                    color_owner=str(Path(color.__file__).resolve()), runtime_owner=str(Path(runtime.__file__).resolve()))
    assert all(snapshot['options'].values())
    assert resources.VERSION == 'scorebug-sprite-v1'
    save('plan.json', {**snapshot, 'plan': dataclasses.asdict(plan)})
    print('PLAN ' + json.dumps(snapshot), flush=True)
    if args.plan_only:
        return 0
    disc = Path(plan.target)
    patch = OUT / (NAME + '.2k5patch')
    if disc.exists() or patch.exists():
        raise FileExistsError('The named test output already exists; preserve it and inspect before retrying.')
    # Check access before removing the oldest image. This creates no disc copy.
    with tempfile.NamedTemporaryFile(prefix='.astra-b71-s9-access-', dir=OUT):
        pass
    images = sorted(OUT.glob('*MOD TEST*.iso'), key=lambda p: (p.stat().st_mtime_ns, p.name))
    patches_before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in OUT.glob('*.2k5patch')}
    removed = []
    while len(images) >= 3:
        oldest = images.pop(0)
        if oldest.is_symlink() or not oldest.is_file():
            raise ValueError('Unexpected MOD TEST image type: ' + str(oldest))
        removed.append(dict(path=str(oldest), size=oldest.stat().st_size, mtime_ns=oldest.stat().st_mtime_ns))
        print('REMOVE_OLDEST_IMAGE ' + str(oldest), flush=True)
        oldest.unlink()
    save('pruning.json', dict(removed=removed, preserved_patches=patches_before))
    last = [None]
    def progress(message, done, total):
        if message != last[0]:
            print(time.strftime('%H:%M:%S') + ' ' + str(message), flush=True)
            last[0] = message
    t0 = time.monotonic()
    disc_verified = False
    try:
        receipt = mb.build(plan, progress)
        save('receipt.json', receipt)
        payload = mb._xbe_bytes(disc)
        readback = dict(scorebug_resources=scorebug.runtime_image_status(disc, probe='sprite'),
                        scorebug_runtime=runtime.status(payload), modern_color_xbe=color.xbe_status(payload),
                        modern_color_bundles=color.image_status(disc), modern_arrowhead=arrowhead.image_status(disc), widescreen=widescreen.status(payload),
                        color_bundle_count=len(color._pins()['bundles']), widescreen_aspect=widescreen.applied_aspect(payload))
        save('readback.json', readback)
        print('READBACK ' + json.dumps(readback), flush=True)
        for key in ('scorebug_resources', 'scorebug_runtime', 'modern_color_xbe', 'modern_color_bundles', 'modern_arrowhead', 'widescreen'):
            assert readback[key] == 'applied', (key, readback[key])
        assert readback['color_bundle_count'] == 477
        assert readback['widescreen_aspect'] == '16:9'
        disc_verified = True
        named = modpack_ops.changed_file_operations(str(BASE), str(disc))
        patch_receipt = modpack.export(str(BASE), str(disc), str(patch),
                                      dict(name=NAME, version='beta-71.1 test p', author='2K5 Mod Studio',
                                           description='Advanced preset with sprite scorebug submission order and coplanar layers, colour, day tuning, linked outside grass, modern Arrowhead, and widescreen. In-game verification pending.'),
                                      overwrite=False, file_operations=named)
        save('patch-receipt.json', patch_receipt)
        for name, identity in patches_before.items():
            path = OUT / name
            assert (path.stat().st_size, path.stat().st_mtime_ns) == identity, name
        assert len(list(OUT.glob('*MOD TEST*.iso'))) <= 3
        result = dict(disc=str(disc), disc_bytes=disc.stat().st_size, patch=str(patch),
                      patch_bytes=patch.stat().st_size, seconds=round(time.monotonic()-t0,3), options=snapshot['options'], readback=readback)
        save('result.json', result)
        print('TESTDISC71_DONE ' + json.dumps(result), flush=True)
    except BaseException:
        # Keep a verified disc if only patch export fails; remove incomplete images.
        if not disc_verified:
            disc.unlink(missing_ok=True)
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
