"""Observe the current bounded XBE union for scratch gates; never build a disc.

Historical disc-only reservations remain explicitly inherited. Every current
XBE writer in the memory gate executes under the real Recorder. Changed PLAY
pairing sources execute through the final-book compiler. The protected Build
orchestrator's XBE IO functions must equal the source pinned by the historical
manifest. This projection is test evidence, not a production disc manifest.
"""
from __future__ import annotations
import ast
from contextlib import ExitStack
import copy
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_read_option_runtime as read
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_cave_manifest as builder
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage, RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_read_option_runtime import XBE

BASE = '77d1c49f682e380b75f1a7290a806a47845608a9'
# These changed sources are covered by the observations below. Any other
# historical fingerprint mismatch requires separate evidence, not a refresh.
REVALIDATED = {'mod_editor/core/'+name+'.py' for name in (
    'mod_build', 'nfl2k5_throw_tuning', 'nfl2k5_espn25_rosters',
    'nfl2k5_my_career_mode', 'nfl2k5_my_career_mode_code',
    'nfl2k5_play_intents', 'nfl2k5_play_library', 'nfl2k5_playbook_pack',
    'nfl2k5_read_option_runtime', 'nfl2k5_read_option_runtime_code')}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded_projection():
    from tests.mod_editor import test_xbe_patch_memory_writes as gate
    if gate.Cs is None:
        raise unittest.SkipTest('Capstone required for the observed XBE gate union')
    from tests import nfl2k5_allocator_stack as stack
    from mod_editor.core import nfl2k5_throw_tuning as tuning
    from tests.mod_editor.test_nfl2k5_read_option_frames import final_reads
    retail = XBE.read_bytes()
    if sha(retail) != RETAIL_SHA256:
        raise unittest.SkipTest('local XBE differs from pinned USA evidence')
    original = DEFAULT_MANIFEST.read_bytes()
    parent = json.loads(original)
    fingerprints = builder.source_fingerprints()
    changed = {name for name, digest in parent['source_sha256'].items()
               if fingerprints.get(name) != digest}
    if not changed <= REVALIDATED:
        raise AssertionError('unobserved source drift: '+str(sorted(changed-REVALIDATED)))
    # The altered Build orchestration does not introduce an unobserved XBE
    # transport. Pin the actual historical source before comparing its AST.
    name = 'mod_editor/core/mod_build.py'
    try:
        old = subprocess.check_output(['git', 'show', BASE+':'+name], cwd=ROOT)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise unittest.SkipTest('historical Build source unavailable for bounded projection') from exc
    if len(old) > 1_000_000 or sha(old) != parent['source_sha256'][name]:
        raise AssertionError('historical Build source pin changed')
    trees = [ast.parse(old), ast.parse((ROOT/name).read_text())]
    for function in ('_xbe_bytes', '_write_xbe_bytes'):
        nodes = [next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
                 for tree in trees]
        if ast.dump(nodes[0]) != ast.dump(nodes[1]):
            raise AssertionError('unobserved XBE transport changed: '+function)
    # Load each explicitly imported gate owner before installing observers.
    modules = {m.__name__: m for m in (*vars(tuning).values(), *vars(stack).values())
               if isinstance(m, ModuleType) and m.__name__.startswith('mod_editor.core.nfl2k5_')}
    tree = ast.parse(inspect.getsource(gate))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'mod_editor.core':
            for alias in node.names:
                if alias.name.startswith('nfl2k5_'):
                    module = importlib.import_module('mod_editor.core.'+alias.name)
                    modules[module.__name__] = module
    modules[tuning.__name__] = tuning
    recorder = builder.Recorder(retail)
    with ExitStack() as scope:
        for module in modules.values():
            for name in ('apply', 'apply_xbe', 'xbe_apply', 'plan_patch', 'apply_arc_table', 'patch_xbe', 'apply_chop_block'):
                function = getattr(module, name, None)
                if inspect.isfunction(function) and function.__module__ == module.__name__:
                    scope.enter_context(patch.object(module, name, recorder.wrapper(module, name)))
        # This adapter captured apply_xbe at import time. Route its real writer
        # through the observer too, rather than only observing later no-op replays.
        from mod_editor.core import nfl2k5_espn25_rosters as espn25
        scope.enter_context(patch.object(espn25.XbePatch, 'apply', staticmethod(espn25.apply_xbe)))
        gate.PatchWriteTests.setUpClass()
        final = gate.PatchWriteTests.patched
    observed = recorder.finish(final)
    # Recompile real native recipes through pools, roles and final pairing.
    resource, table, pairing = final_reads()
    required = {read.OWNER, 'nfl2k5_espn25_rosters', 'nfl2k5_my_career_mode', 'nfl2k5_throw_tuning'}
    if not required <= {step['owner'] for step in recorder.steps if step['changed_bytes']}:
        raise AssertionError('a changed writer was not observed')
    if fingerprints != builder.source_fingerprints():
        raise AssertionError('sources changed during bounded projection')
    layout = space.layout(final)
    inherited = [row for row in parent['spans'] if int(row['start'], 0) < space.CODE_VA]
    unique = {(row['start'], row['end'], row['owner'], row['basis']): row for row in inherited+observed}
    loaded = {str(Path(m.__file__).resolve()) for m in tuple(sys.modules.values()) if getattr(m, '__file__', None)}
    used = {name: digest for name, digest in fingerprints.items()
            if name in parent['source_sha256'] or str((ROOT/name).resolve()) in loaded}
    result = copy.deepcopy(parent)
    result.update(model='TEST ONLY: observed current XBE gate union and final PLAY compiler; inherited disc-only evidence',
                  spans=sorted(unique.values(), key=lambda r: (int(r['start'],0), int(r['end'],0), r['owner'])),
                  source_sha256=used, allocator_layout=layout,
                  stack_image_size=XbeImage(final).image_size, stack_xbe_sha256=sha(final))
    result['read_option_v5_revalidation'] = dict(parent_manifest_sha256=sha(original),
        original_source_sha256=parent['source_sha256'], changed_sources=sorted(changed),
        observed_steps=recorder.steps, pairing=pairing, final_play_sha256=sha(resource),
        table_sha256=sha(table), build_xbe_io_ast_unchanged=True,
        inherited_disc_fields=True, new_disc_built=False, release_manifest=False,
        runtime_witnessed=False, production_regeneration_required=True)
    ReservationManifest(result, XbeImage(retail), source_root=ROOT)
    if DEFAULT_MANIFEST.read_bytes() != original:
        raise AssertionError('protected manifest changed')
    return final, result


@unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE required')
class OwnershipRevalidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.final, cls.document = bounded_projection()

    def test_complete_owner_and_seventh_live_hook_are_observed(self):
        manifest = ReservationManifest(self.document, XbeImage(XBE.read_bytes()), source_root=ROOT)
        for name, (va, old) in read.HOOKS.items():
            self.assertTrue(manifest.overlaps(va, va+len(old)), name)
            self.assertFalse(manifest.overlaps(va, va+len(old), exclude_owner=read.OWNER), name)
        self.assertEqual(len(read.HOOKS), 7)
        self.assertFalse(self.document['read_option_v5_revalidation']['new_disc_built'])
        self.assertEqual(read.apply(self.final)[0], self.final)

    def test_both_variants_keep_identical_reservations_and_strict_source_pins(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        retail = XBE.read_bytes()
        seed = space.apply(retail, REQUESTS, scaleout=True)[0]
        normal = read.apply(seed)[0]
        diagnostic = read.apply(seed, diagnostic=True)[0]
        self.assertEqual(read.reservations(normal), read.reservations(diagnostic))
        self.assertEqual(space.layout(normal), space.layout(diagnostic))
        bad = copy.deepcopy(self.document)
        bad['source_sha256']['mod_editor/core/nfl2k5_read_option_runtime.py'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'stale reservation source'):
            ReservationManifest(bad, XbeImage(retail), source_root=ROOT)

    @classmethod
    def tearDownClass(cls):
        if output := os.environ.get('NFL2K5_READ_OPTION_V5_MANIFEST'):
            path = Path(output).resolve()
            if not path.is_relative_to((ROOT/'.scratch').resolve()):
                raise AssertionError('test manifest output must remain in .scratch')
            path.write_text(json.dumps(cls.document, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
