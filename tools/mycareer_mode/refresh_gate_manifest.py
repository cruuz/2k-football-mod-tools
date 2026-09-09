"""Refresh MyCareer-only gate reservations without making a disc copy.

Development fallback for the 100 GB free-space floor. This is a conservative
incremental manifest, NOT a regenerated release/disc manifest. Every unchanged
parent source pin must match. Changed sources must match the parent manifest
at the pinned base revision, and be exactly the two MyCareer mode Python modules. Fresh native
hook reservations come from the oracle Recorder observing the actual writer.
Existing parent allocations and reservations are retained; none is freed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE_REVISION = '77d1c49f682e380b75f1a7290a806a47845608a9'
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode, nfl2k5_my_career as owner
from mod_editor.core import nfl2k5_cave_manifest as oracle
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256


def refresh(xbe, output, base_revision=BASE_REVISION):
    output = Path(output).resolve()
    if ROOT / '.scratch' not in output.parents:
        raise ValueError('incremental manifest must remain under this worktree .scratch')
    xbe = Path(xbe)
    if xbe.stat().st_size > 16 * 1024**2:
        raise ValueError('XBE exceeds 16 MiB')
    retail = xbe.read_bytes()
    if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        raise ValueError('retail XBE pin differs')
    parent = ROOT / 'data/nfl2k5_cave_reservations.json'
    document = json.loads(parent.read_text(encoding='utf-8'))
    base_revision = subprocess.check_output(
        ['git', 'rev-parse', '--verify', base_revision + '^{commit}'], cwd=ROOT,
        text=True).strip()
    allowed = {'mod_editor/core/nfl2k5_my_career_mode.py',
               'mod_editor/core/nfl2k5_my_career_mode_code.py'}
    fingerprints = oracle.source_fingerprints()
    changed = []
    for path, digest in document['source_sha256'].items():
        if fingerprints.get(path) == digest:
            continue
        if path not in allowed:
            raise ValueError(f'non-MyCareer source pin differs: {path}')
        baseline = subprocess.check_output(['git', 'show', base_revision + ':' + path], cwd=ROOT)
        if hashlib.sha256(baseline).hexdigest() != digest:
            raise ValueError(f'parent manifest does not cover base revision: {path}')
        changed.append(path)
    requests = [(a['owner'], a['kind'], a['size'], a['align'])
                for a in document['allocator_layout']['allocations']
                if a['owner'] not in (mode.space.OWNER, mode.space.DIRECTORY_OWNER, 'nfl2k5_music_metadata')]
    before, _ = mode.space.apply(retail, requests, scaleout=True)
    after, receipt = mode.apply(before)
    if mode.status(after) != 'applied' or mode.apply(after)[0] != after:
        raise ValueError('fresh MyCareer install/replay differs')
    recorder = oracle.Recorder(retail)
    recorder.observe(owner, 'mode.apply incremental probe', before, after, receipt)
    added = [s for s in recorder.spans if int(s['start'], 0) < mode.space.CODE_VA]
    document['spans'].extend(added)
    document['steps'].extend(recorder.steps)
    document['source_sha256'].update({p: fingerprints[p] for p in changed})
    document['model'] = ('BOUNDED XBE PROJECTION: unchanged parent reservations plus '
                         'observed MyCareer mode 5 writes; no new disc build')
    document['mycareer_incremental_proof'] = dict(
        parent_manifest_sha256=hashlib.sha256(parent.read_bytes()).hexdigest(),
        parent_source_revision=base_revision,
        parent_disc_fields_are_historical=True, disc_built=False,
        release_manifest=False, changed_sources=sorted(changed),
        added_retail_reservations=len(added), observed_probe=recorder.steps,
        fixed_rx=8192, fixed_rw=4096,
        reason='A full disc copy would violate the 100 GB free-space floor.')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    return document['mycareer_incremental_proof']


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('xbe', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--base-revision', default=BASE_REVISION,
                   help='revision whose changed sources match the parent manifest')
    a = p.parse_args()
    print(json.dumps(refresh(a.xbe, a.output, a.base_revision), indent=2))
