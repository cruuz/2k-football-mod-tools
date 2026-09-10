#!/usr/bin/env python3
"""Scratch-only star reservation revalidation; never a release manifest regen.

Require every other source fingerprint unchanged, the parent's star source
pin at the beta-64 baseline, and every declared/new write covered by the
existing star reservations. Observe the actual filled writer and retain all
parent reservations. No disc or game executable is written.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_player_star as ps
from mod_editor.core.nfl2k5_cave_manifest import Recorder, source_fingerprints
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, RETAIL_SHA256, ReservationManifest, XbeImage
from tools.player_star.audit import RETAIL

BASE = 'c9d01941'
SOURCE = 'mod_editor/core/nfl2k5_player_star.py'


def refresh(output: Path):
    output = output.resolve()
    if (ROOT/'.scratch').resolve() not in output.parents:
        raise ValueError('test manifest must stay under this worktree .scratch')
    retail = RETAIL.read_bytes()
    if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        raise ValueError('retail pin differs')
    parent = DEFAULT_MANIFEST.read_bytes()
    document = json.loads(parent)
    manifest = ReservationManifest(document, XbeImage(retail))
    pins = source_fingerprints()
    changed = {p for p, digest in document['source_sha256'].items() if pins.get(p) != digest}
    if changed != {SOURCE}:
        raise ValueError(f'expected only the star writer source to drift: {sorted(changed)}')
    # The release parent fingerprints a subset of the helper sources. Check
    # the entire current source list against beta 64 as well, without adding
    # unobserved ownership claims for helpers outside that parent subset.
    tracked = subprocess.check_output(['git', 'ls-files', '--', *pins], cwd=ROOT, text=True)
    if not set(pins) <= set(tracked.splitlines()):
        raise ValueError('untracked writer/helper source is outside the baseline')
    diff = subprocess.check_output(['git', 'diff', '--name-only', BASE, '--', *pins], cwd=ROOT, text=True)
    if set(diff.splitlines()) != {SOURCE}:
        raise ValueError('another writer/helper changed since beta 64')
    baseline = subprocess.check_output(['git', 'show', BASE+':'+SOURCE], cwd=ROOT)
    if hashlib.sha256(baseline).hexdigest() != document['source_sha256'][SOURCE]:
        raise ValueError('parent star fingerprint does not match beta 64')

    def covered(start, end):
        rows = sorted((int(s['start'], 0), int(s['end'], 0)) for s in document['spans']
                      if s['owner'] == 'nfl2k5_player_star')
        cursor = start
        for a, b in rows:
            if a <= cursor < b:
                cursor = b
        if cursor < end or manifest.overlaps(start, end, exclude_owner='nfl2k5_player_star'):
            raise ValueError(f'new or conflicting star reservation: {start:#x}..{end:#x}')

    for _, va, code in ps.sites():
        if va == ps.GATE_VA and code == ps._read(retail, va, len(code)):
            continue  # unchanged live gate; legacy upgrade restores exact retail
        covered(va, va+len(code))
    patched, receipt = ps.apply(retail)
    if ps.status(patched) != 'applied' or ps.apply(patched)[0] != patched:
        raise ValueError('filled writer failed verification/replay')
    recorder = Recorder(retail)
    recorder.observe(ps, 'apply: filled star footprint revalidation', retail, patched, receipt)
    document['source_sha256'][SOURCE] = pins[SOURCE]
    document['steps'].extend(recorder.steps)
    document['star_filled_revalidation'] = dict(
        release_manifest=False, disc_built=False, parent_disc_fields_are_historical=True,
        parent_manifest_sha256=hashlib.sha256(parent).hexdigest(), baseline=BASE,
        changed_sources=sorted(changed), reservations_unchanged=True,
        observed_steps=recorder.steps,
    )
    document['model'] = 'TEST ONLY: unchanged parent reservations and observed filled-star XBE writes; no disc build'
    ReservationManifest(document, XbeImage(retail), source_root=ROOT)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(document, indent=2)+'\n').encode())
    return document['star_filled_revalidation']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(refresh(parser.parse_args().output), indent=2))
