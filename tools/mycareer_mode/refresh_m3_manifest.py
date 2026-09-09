"""Conservative XBE-only M3 gate projection. Never a release/disc manifest.

Retains all parent retail reservations and observes current changed owners.
Replaces only named grown allocations with their newly sealed request union.
Historical image fields remain explicitly historical. Output must be scratch.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def refresh(xbe, output):
    from mod_editor.core import nfl2k5_cave_manifest as oracle
    from mod_editor.core import nfl2k5_xbe_space as space
    from mod_editor.core import nfl2k5_my_career_mode as mode
    from mod_editor.core import nfl2k5_read_option_runtime as read_option
    from mod_editor.core import nfl2k5_espn25_rosters as espn
    from mod_editor.core import nfl2k5_coverage_trail as trail
    from mod_editor.core import nfl2k5_music_metadata as music
    from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage, ReservationManifest
    from tests.nfl2k5_allocator_stack import REQUESTS, SONGS
    output = Path(output).resolve()
    if ROOT / '.scratch' not in output.parents:
        raise ValueError('projection must remain under this worktree .scratch')
    with Path(xbe).open('rb') as stream:
        retail = stream.read(16 * 1024**2 + 1)
    if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        raise ValueError('USA retail XBE pin differs')
    parent = ROOT / 'data/nfl2k5_cave_reservations.json'
    document = json.loads(parent.read_text())
    # Validate the complete old reservation geometry and retail identity first.
    ReservationManifest(document, XbeImage(retail))
    recorder = oracle.Recorder(retail)
    payload = recorder.wrapper(space, 'apply')(retail, REQUESTS, scaleout=True)[0]
    payload = recorder.wrapper(music, 'apply')(payload, song_records=SONGS)[0]
    for module, function in ((mode, 'apply'), (read_option, 'apply'),
                             (espn, 'apply_xbe'), (trail, 'apply')):
        payload = recorder.wrapper(module, function)(payload)[0]
    fresh = recorder.finish(payload)
    old = document['allocator_layout']['allocations']
    spans = []
    for span in document['spans']:
        a, b = int(span['start'], 0), int(span['end'], 0)
        if a < space.CODE_VA:
            spans.append(span)
        elif span['owner'] == space.OWNER:
            continue  # complete grown parent pages come from the current seal
        elif not any(r['owner'] == span['owner'] and r['va'] <= a < b <= r['va'] + r['size'] for r in old):
            raise ValueError('parent has an unrecognized grown child reservation')
    spans.extend(fresh)
    unique = {(s['start'], s['end'], s['owner'], s['basis']): s for s in spans}
    document['spans'] = sorted(unique.values(), key=lambda s: (int(s['start'], 0), int(s['end'], 0), s['owner']))
    pins = oracle.source_fingerprints()
    changed = sorted(p for p, digest in document['source_sha256'].items() if pins.get(p) != digest)
    document['source_sha256'] = pins
    document['allocator_layout'] = space.layout(payload)
    document['steps'].extend(recorder.steps)
    document['model'] = 'BOUNDED XBE PROJECTION: parent retail reservations and observed current owners; no disc build'
    document['mycareer_m3_projection'] = {
        'release_manifest': False, 'disc_built': False, 'parent_disc_fields_are_historical': True,
        'parent_manifest_sha256': hashlib.sha256(parent.read_bytes()).hexdigest(),
        'changed_sources': changed, 'observed_steps': recorder.steps,
        'code_bytes_reserved': mode.CODE_SIZE, 'writable_bytes_reserved': 8192,
        'reason': 'A disposable disc copy cannot retain the required 100 GB free space.',
    }
    ReservationManifest(document, XbeImage(retail), source_root=ROOT)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    return {'spans': len(document['spans']), 'changed_sources': changed, 'disc_built': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xbe', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(refresh(args.xbe, args.output), indent=2))
