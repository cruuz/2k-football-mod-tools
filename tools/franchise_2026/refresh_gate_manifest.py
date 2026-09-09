"""Scratch-only XBE reservation revalidation for the r65 base.

No disc is copied. Retain the historical parent reservations, observe the
changed native owners, and relocate named allocations through the existing
strict gate helper. This is not a regenerated release/disc manifest.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_cave_manifest as builder
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, RETAIL_SHA256, ReservationManifest, XbeImage
from mod_editor.core import nfl2k5_franchise_2026 as franchise
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_my_career as career
from mod_editor.core import nfl2k5_read_option_runtime as read
from tests import nfl2k5_allocator_stack as stack
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import prerequisites

BASE = '77d1c49f682e380b75f1a7290a806a47845608a9'
CHANGED = {
    'mod_editor/core/mod_build.py', 'mod_editor/core/nfl2k5_throw_tuning.py',
    'mod_editor/core/nfl2k5_espn25_rosters.py', 'mod_editor/core/nfl2k5_franchise_2026.py',
    'mod_editor/core/nfl2k5_my_career_mode.py', 'mod_editor/core/nfl2k5_my_career_mode_code.py',
    'mod_editor/core/nfl2k5_read_option_runtime.py', 'mod_editor/core/nfl2k5_read_option_runtime_code.py',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def refresh(xbe, output):
    output = Path(output).resolve()
    if (ROOT / '.scratch').resolve() not in output.parents:
        raise ValueError('test manifest must remain under this worktree .scratch')
    with Path(xbe).open('rb') as stream:
        retail = stream.read(16 * 1024**2 + 1)
    if len(retail) > 16 * 1024**2 or sha(retail) != RETAIL_SHA256:
        raise ValueError('bounded USA retail XBE pin differs')
    parent_bytes = DEFAULT_MANIFEST.read_bytes()
    document = json.loads(parent_bytes)
    fingerprints = builder.source_fingerprints()
    changed = {p for p, digest in document['source_sha256'].items() if fingerprints.get(p) != digest}
    if not changed <= CHANGED:
        raise ValueError('unreviewed changed sources: ' + ', '.join(sorted(changed - CHANGED)))
    for path in changed:
        baseline = subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)
        if sha(baseline) != document['source_sha256'][path]:
            raise ValueError('parent source does not match pinned beta-62 baseline: ' + path)

    # The task changes only the inspection API. Compare the actual writer with
    # the manifest-pinned implementation at two different allocator placements.
    name = 'mod_editor.core._franchise_2026_manifest_baseline'
    old = types.ModuleType(name)
    old.__package__ = 'mod_editor.core'
    sys.modules[name] = old
    source = subprocess.check_output(['git', 'show', BASE + ':mod_editor/core/nfl2k5_franchise_2026.py'], cwd=ROOT)
    try:
        exec(compile(source, BASE + ':franchise_2026.py', 'exec'), old.__dict__)
        if old.REQUESTS != franchise.REQUESTS:
            raise ValueError('Franchise-2026 budget changed')
        for requests in (franchise.REQUESTS, stack.REQUESTS):
            seed = stack.space.apply(retail, requests, scaleout=True)[0]
            if old.apply(seed)[0] != franchise.apply(seed)[0]:
                raise ValueError('Franchise-2026 native bytes changed')
    finally:
        del sys.modules[name]

    seed = stack.space.apply(prerequisites(retail), stack.REQUESTS, scaleout=True)[0]
    seed = stack.music.apply(seed, song_records=stack.SONGS)[0]
    recorder = builder.Recorder(retail)
    observed = seed
    for owner, operation, options in (
        (career, mode.apply, {}), (read, read.apply, dict(diagnostic=True)),
        (stack.espn25, stack.espn25.apply_xbe, {}),
        (stack.coverage_trail, stack.coverage_trail.apply, {}),
        (franchise, franchise.apply, {}),
    ):
        after, receipt = operation(observed, **options)
        if operation(after, **options)[0] != after:
            raise ValueError('observed writer failed replay: ' + owner.__name__)
        recorder.observe(owner, 'r65 bounded revalidation', observed, after, receipt)
        observed = after
    # Never place current-union child bytes into the parent's old layout. Its
    # named allocations are transformed by the gate helper, with strict sizes.
    document['spans'] += [s for s in recorder.spans if int(s['start'], 0) < stack.space.CODE_VA]
    document = stack.manifest_for_allocated_union(
        ReservationManifest(document, XbeImage(retail)), retail, observed).document
    document['source_sha256'] = fingerprints
    document['model'] = 'TEST ONLY: historical reservations plus observed r65 XBE writes; no disc build'
    document['franchise_2026_revalidation'] = dict(
        base_revision=BASE, parent_manifest_sha256=sha(parent_bytes), changed_sources=sorted(changed),
        release_manifest=False, disc_built=False, parent_disc_fields_are_historical=True,
        franchise_native_bytes_equal_parent=True, observations=recorder.steps,
        reason='Disposable disc copy cannot retain the required 100 GB free space.')
    ReservationManifest(document, XbeImage(retail), source_root=ROOT)
    if DEFAULT_MANIFEST.read_bytes() != parent_bytes:
        raise ValueError('protected manifest changed during revalidation')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    return dict(output=str(output.relative_to(ROOT)), spans=len(document['spans']),
                changed_sources=sorted(changed), observed_steps=len(recorder.steps), disc_built=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xbe', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(refresh(args.xbe, args.output), indent=2))
