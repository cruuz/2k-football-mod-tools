"""Observe current XBE writers without a disc copy. Not a production manifest.

Uses the existing Recorder and complete memory-gate stack, as the Guardian
manifest proof does. An independent season-rules probe reserves its legacy
owners too. Nothing is inherited or repinned from the stale release JSON.
"""
from pathlib import Path
import ast
from contextlib import ExitStack
import copy
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
import sys
import unittest
from unittest.mock import patch as wrap

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_cave_manifest as builder
from mod_editor.core import nfl2k5_season_length as season
from mod_editor.core.nfl2k5_cave_oracle import MANIFEST_SCHEMA, RETAIL_SHA256, XbeImage, ReservationManifest, OracleError
from tests.mod_editor import test_xbe_patch_memory_writes as gate


def observe():
    if not gate.XBE.is_file() or importlib.util.find_spec('capstone') is None:
        raise unittest.SkipTest('retail USA XBE and Capstone required for observed owner manifest')
    retail = gate.XBE.read_bytes()
    if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        raise unittest.SkipTest('local XBE does not match the USA retail pin')
    for file in (ROOT/'tests/mod_editor/test_xbe_patch_memory_writes.py',ROOT/'tests/nfl2k5_allocator_stack.py'):
        for node in ast.walk(ast.parse(file.read_text())):
            if isinstance(node,ast.ImportFrom) and node.module=='mod_editor.core':
                for alias in node.names: importlib.import_module(node.module+'.'+alias.name)
    engines = {'mod_editor.core.nfl2k5_gameplay_lever','mod_editor.core.nfl2k5_rdata_sites'}
    modules = [m for name,m in tuple(sys.modules.items()) if name.startswith('mod_editor.core.nfl2k5_')
               and name not in engines and hasattr(m,'__file__')]
    fingerprint = builder.source_fingerprints()
    recorder = builder.Recorder(retail)
    with ExitStack() as context:
        for module in modules:
            for name in ('apply','apply_xbe','xbe_apply','plan_patch','apply_arc_table','patch_xbe','apply_chop_block'):
                function = getattr(module,name,None)
                if inspect.isfunction(function) and function.__module__ == module.__name__:
                    context.enter_context(wrap.object(module,name,recorder.wrapper(module,name)))
            # The ESPN importer exposes a static alias captured at import time.
            # Point that test-only alias at the same observed real writer so its
            # 12-byte live edit is attributed too; no product code is changed.
            if module.__name__ == 'mod_editor.core.nfl2k5_espn25_rosters':
                context.enter_context(wrap.object(module.XbePatch,'apply',staticmethod(module.apply_xbe)))
        # Alternate fixed-span rules are observed from retail before the full
        # gate. They are not mislabeled as installed on the final owner union.
        season.apply(retail)
        gate.PatchWriteTests.setUpClass()
        final = gate.PatchWriteTests.patched
    spans = recorder.finish(final)  # fails on any unobserved changed byte
    if fingerprint != builder.source_fingerprints():
        raise OracleError('sources changed during observed XBE composition')
    document = dict(schema=MANIFEST_SCHEMA,retail_sha256=RETAIL_SHA256,complete=True,
                    model='Observed complete XBE safety-gate composition plus alternate season rules; no disc or resource build',
                    stack_image_size=XbeImage(final).image_size,stack_xbe_sha256=hashlib.sha256(final).hexdigest(),
                    section_digests_verified=True,source_sha256=fingerprint,spans=spans,steps=recorder.steps,
                    allocator_layout=abilities.space.layout(final),runtime_witnessed=False,
                    real_disc_build=False,production_regeneration_required=True,
                    # Retain the oracle's historical step vocabulary, explicitly
                    # scoped to observed XBE phases rather than disc transport.
                    image_steps=['season_2026','scorebug_runtime'],
                    image_steps_scope='XBE probes only; season rules use an alternate retail seed')
    ReservationManifest(document,XbeImage(retail),source_root=ROOT)
    return retail, final, document


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail, cls.final, cls.document = observe()
        target = os.environ.get('NFL2K5_ABILITIES_MANIFEST_OUTPUT')
        if target:
            path = Path(target).resolve()
            if not path.is_relative_to((ROOT/'.scratch').resolve()):
                raise ValueError('private proof manifest must stay in this worktree .scratch')
            path.write_text(json.dumps(cls.document,indent=2)+'\n')

    def test_every_hook_and_complete_owned_code_observed_with_no_other_hook_owner(self):
        manifest = ReservationManifest(self.document,XbeImage(self.retail),source_root=ROOT)
        self.assertFalse(self.document['real_disc_build'])
        self.assertTrue(self.document['production_regeneration_required'])
        self.assertEqual(abilities.read_settings(self.final)['model_version'],2)
        for _,(va,before) in abilities.HOOKS.items():
            self.assertTrue(manifest.overlaps(va,va+len(before)))
            self.assertEqual(manifest.overlaps(va,va+len(before),exclude_owner=abilities.OWNER),[])
        allocation = abilities.allocation(self.final)
        self.assertTrue(any(r['owner']==abilities.OWNER and int(r['start'],0)==allocation['va']
                            and r['size']==abilities.CODE_SIZE for r in self.document['spans']))

    def test_fresh_source_validation_refuses_changed_abilities_and_momentum(self):
        for owner in ('abilities_runtime','momentum'):
            broken = copy.deepcopy(self.document)
            broken['source_sha256'][f'mod_editor/core/nfl2k5_{owner}.py'] = '0'*64
            with self.assertRaisesRegex(OracleError,'stale reservation source'):
                ReservationManifest(broken,XbeImage(self.retail),source_root=ROOT)


if __name__ == '__main__': unittest.main()
