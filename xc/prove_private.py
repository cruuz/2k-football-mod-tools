#!/usr/bin/env python3
"""DESIGN: after standalone proof, exercise the actual private-build mover on D.

Reuses the one authorized output path; never writes the input image. Removes
the proved standalone copy first, so two full images never coexist here.
"""
from pathlib import Path
import json
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "xc")]
from mod_editor.core import build_io, xdvdfs_compact as compact
from prove_disc import digest

SOURCE = Path('/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 candidate D 2026-09-28.xiso.iso')
OUTPUT = Path('/media/noah/Storage/.b76-research/xc/astra-build/candidate-D-compact.xiso.iso')
EVIDENCE = ROOT / 'xc/evidence'


def main():
    proof = json.loads((EVIDENCE / 'disc-proof.json').read_text())
    assert proof['studio_inspection_equal'] and proof['input_matches_published_build_receipt']
    assert digest(OUTPUT) == proof['output']
    assert shutil.disk_usage(ROOT).free > 100_000_000_000
    OUTPUT.unlink()
    assert shutil.disk_usage(OUTPUT.parent).free > SOURCE.stat().st_size + 1_000_000_000
    last = 0.0

    def progress(stage, done, total):
        nonlocal last
        now = time.monotonic()
        if now - last > 10:
            print(f'DESIGN: {stage}: {done:,}/{total:,}', flush=True)
            last = now

    build_io.copy_image(SOURCE, OUTPUT, progress)
    result = compact.finish_private(OUTPUT, original=SOURCE, progress=progress)
    actual = digest(OUTPUT)
    assert actual == proof['output'], (actual, proof['output'])
    result['whole_image_matches_standalone'] = True
    result['output'] = actual
    result['nvme_free_bytes'] = shutil.disk_usage(ROOT).free
    (EVIDENCE / 'private-build-proof.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PROVED OFFLINE: private build compaction matches the standalone image byte for byte', flush=True)
    OUTPUT.unlink()
    for suffix in compact.STUDIO_RECEIPTS:
        Path(str(OUTPUT) + suffix).unlink(missing_ok=True)
    cleanup = dict(classification='PROVED OFFLINE', output_deleted=not OUTPUT.exists(),
                   nvme_free_bytes=shutil.disk_usage(ROOT).free,
                   storage_free_bytes=shutil.disk_usage(OUTPUT.parent).free)
    (EVIDENCE / 'cleanup.json').write_text(json.dumps(cleanup, indent=2) + '\n')
    print('PROVED OFFLINE: ' + json.dumps(cleanup), flush=True)


if __name__ == '__main__':
    main()
