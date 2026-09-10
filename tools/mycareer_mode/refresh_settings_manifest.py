"""Scratch-only integrated beta-65 XBE projection; never a disc-build receipt.

Observe the complete forward XBE safety-gate stack, retaining every historical
retail reservation and re-sealing grown ownership from its actual directory.
Changed XBE writers must be observed. Four helper/dispatcher pins are snapshots
for drift detection, explicitly not renewed evidence for their other APIs.
"""
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import argparse
import hashlib
import inspect
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_cave_manifest as oracle
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
from tests.mod_editor.test_xbe_patch_cave_references import CaveReferenceTests
from tests.nfl2k5_allocator_stack import owner_calls
from tests.nfl2k5_supersim_draft_fixture import retail_bytes

# These are not independent pure-byte owners in this probe. Their other APIs
# (including the legacy binder writer and disc dispatcher) are not recertified.
# Current pins detect drift; mode.apply observes the current binder usage.
NON_XBE = {
    'mod_editor/core/mod_build.py': 'disc/preset wiring remains unwitnessed by this XBE projection',
    'mod_editor/core/nfl2k5_roster_records.py': 'roster reader; no XBE mutation',
    'mod_editor/core/nfl2k5_my_career_save.py': 'footer codec; bounded native/host round-trip tests',
    'mod_editor/core/nfl2k5_my_career.py': 'binder prerequisite/helper used by observed mode writer',
}
# Reject drift outside the integrated beta-65 changes plus this Settings job.
CHANGED_WRITERS = {
    'nfl2k5_edge_rename', 'nfl2k5_franchise_edit_player', 'nfl2k5_modern_positions',
    'nfl2k5_my_career_mode', 'nfl2k5_my_career_mode_code', 'nfl2k5_player_star',
    'nfl2k5_position_pools', 'nfl2k5_throw_tuning', 'nfl2k5_xbe_space',
}
SHARED_HELPERS = {'nfl2k5_rdata_sites', 'nfl2k5_gameplay_lever'}


def refresh(output):
    output = Path(output).resolve()
    if (ROOT/'.scratch').resolve() not in output.parents:
        raise ValueError('projection must remain under this worktree .scratch')
    retail = retail_bytes()
    parent_bytes = DEFAULT_MANIFEST.read_bytes()
    document = json.loads(parent_bytes)
    ReservationManifest(document, XbeImage(retail))
    pins = oracle.source_fingerprints()
    changed = {p for p, digest in document['source_sha256'].items() if pins.get(p) != digest}
    allowed = set(NON_XBE) | {f'mod_editor/core/{n}.py' for n in CHANGED_WRITERS}
    if changed-allowed:
        raise ValueError(f'unaccounted source changes: {sorted(changed-allowed)}')
    # Load all pure-byte owners before wrapping their public mutation entries.
    from mod_editor.core import nfl2k5_throw_tuning as tt
    from mod_editor.core import nfl2k5_modern_positions as positions
    from mod_editor.core import nfl2k5_position_pools as pools
    owner_calls()
    modules = {m.__name__: m for m in tuple(sys.modules.values()) if isinstance(m, ModuleType)
               and m.__name__.startswith('mod_editor.core.nfl2k5_')
               and m.__name__.split('.')[-1] not in SHARED_HELPERS}
    recorder = oracle.Recorder(retail)
    with ExitStack() as stack:
        for module in modules.values():
            for name in ('apply', 'apply_xbe', 'xbe_apply', 'plan_patch', 'apply_arc_table', 'patch_xbe', 'apply_chop_block'):
                function = getattr(module, name, None)
                if inspect.isfunction(function) and function.__module__ == module.__name__:
                    stack.enter_context(patch.object(module, name, recorder.wrapper(module, name)))
        # The same constructor used by both gate orders; no checks are mocked.
        CaveReferenceTests.setUpClass()
        final = CaveReferenceTests.patched
        # Optional modern-position profile shares retail reservations but is
        # outside the default gate seed. Observe its independent pure-byte pass.
        positions.apply(retail)
    steps = {r['owner'] for r in recorder.steps}
    # Generic write helpers carry their caller's ownership. Recording them
    # independently would invent competing reservations for the very same edit.
    if steps & SHARED_HELPERS:
        raise ValueError('generic helper was incorrectly recorded as an owner')
    for source in changed-set(NON_XBE):
        name = Path(source).stem
        required = 'nfl2k5_my_career' if name.startswith('nfl2k5_my_career_mode') else name
        if required not in steps:
            raise ValueError(f'changed writer was not observed: {source}')
    fresh = recorder.finish(final)
    old = document['allocator_layout']['allocations']
    kept = []
    for row in document['spans']:
        start, end = int(row['start'], 0), int(row['end'], 0)
        if start < space.CODE_VA:
            kept.append(row)
        elif row['owner'] != space.OWNER and not any(
                a['owner'] == row['owner'] and a['va'] <= start < end <= a['va']+a['size'] for a in old):
            raise ValueError(f'unrecognized inherited grown reservation: {row}')
    unique = {(r['start'], r['end'], r['owner'], r['basis']): r for r in kept+fresh}
    document.update(model='BOUNDED INTEGRATED BETA-65 XBE PROJECTION; historical retail reservations and observed forward gate stack; no disc build',
                    spans=sorted(unique.values(), key=lambda r: (int(r['start'], 0), int(r['end'], 0), r['owner'])),
                    allocator_layout=space.layout(final), source_sha256=pins,
                    stack_xbe_sha256=hashlib.sha256(final).hexdigest(), stack_image_size=XbeImage(final).image_size)
    document['steps'].extend(recorder.steps)
    document['settings_projection'] = dict(release_manifest=False, disc_built=False, runtime_witnessed=False,
        parent_manifest_sha256=hashlib.sha256(parent_bytes).hexdigest(), parent_disc_fields_are_historical=True,
        changed_sources=sorted(changed), non_xbe_snapshot_reasons=NON_XBE,
        observed_steps=recorder.steps, production_regeneration_required=True)
    if pins != oracle.source_fingerprints():
        raise ValueError('sources changed during observation')
    ReservationManifest(document, XbeImage(retail), source_root=ROOT)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(document, indent=2)+'\n').encode())
    return dict(spans=len(document['spans']), observed_steps=len(recorder.steps), disc_built=False,
                changed_sources=sorted(changed), manifest_sha256=hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(refresh(parser.parse_args().output), indent=2))
