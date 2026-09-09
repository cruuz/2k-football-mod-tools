"""Observe a fresh XBE-only stack when the free-space floor forbids a disc copy.

This test does not inherit stale source pins or certify archive/disc writers.
It records the actual current gate composition with the production Recorder.
An optional scratch JSON enables the unchanged source-freshness oracle checks.
The protected release manifest still requires Claude's real disc rebuild.
"""
from contextlib import ExitStack
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tests.mod_editor.test_nfl2k5_playbook_pair import XBE
from mod_editor.core import nfl2k5_playbook_pair as pair
from mod_editor.core import nfl2k5_cave_manifest as manifest
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage, ReservationManifest, DEFAULT_MANIFEST, MANIFEST_SCHEMA


@unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE is absent')
class XbeManifestTests(unittest.TestCase):
    def test_fresh_observed_xbe_union_without_a_disc_copy(self):
        from tests.mod_editor.test_xbe_patch_memory_writes import PatchWriteTests, Cs
        if Cs is None:
            self.skipTest('capstone is required by the complete XBE gate fixture')
        from tests import nfl2k5_allocator_stack  # load all union modules before wrapping
        from mod_editor.core import nfl2k5_throw_tuning, nfl2k5_season_length
        from mod_editor.core import nfl2k5_depth_chart_rows, nfl2k5_position_pools
        from mod_editor.core import nfl2k5_modern_naming, nfl2k5_throw_arc
        from mod_editor.core import nfl2k5_espn25_rosters as espn25, nfl2k5_coverage_trail as trail
        del nfl2k5_allocator_stack, nfl2k5_throw_tuning, nfl2k5_season_length
        del nfl2k5_depth_chart_rows, nfl2k5_position_pools, nfl2k5_modern_naming, nfl2k5_throw_arc
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest()!=RETAIL_SHA256:
            self.skipTest('USA retail XBE hash differs')
        protected = DEFAULT_MANIFEST.read_bytes()
        sources = manifest.source_fingerprints()
        recorder = manifest.Recorder(retail)
        # These helpers accept sites from their callers; they are not owners.
        # Record the outer writer, or its adapter, instead of assigning those
        # same bytes a second, incorrect helper owner.
        helpers = {'mod_editor.core.nfl2k5_rdata_sites', 'mod_editor.core.nfl2k5_gameplay_lever'}
        modules = [m for name,m in tuple(sys.modules.items())
                   if name.startswith('mod_editor.core.nfl2k5_') and name not in helpers]
        with ExitStack() as stack:
            for module in modules:
                for name in ('apply','apply_xbe','xbe_apply','plan_patch','apply_arc_table','patch_xbe','apply_chop_block'):
                    function=getattr(module,name,None)
                    if inspect.isfunction(function) and function.__module__==module.__name__:
                        stack.enter_context(patch.object(module,name,recorder.wrapper(module,name)))
            # The gate adapter captured the original function at import time.
            # Make it call the wrapped writer while this observation is active.
            stack.enter_context(patch.object(espn25.XbePatch,'apply',staticmethod(espn25.apply_xbe)))
            PatchWriteTests.setUpClass()
        final = PatchWriteTests.patched
        spans = recorder.finish(final)
        self.assertEqual(pair.status(final),'applied')
        self.assertEqual(sources,manifest.source_fingerprints())
        self.assertEqual(DEFAULT_MANIFEST.read_bytes(),protected)
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        for section in _sections(final):
            self.assertEqual(final[section.header_offset+36:section.header_offset+56],
                             section_digest(final,section),section.index)
        document = dict(schema=MANIFEST_SCHEMA, retail_sha256=RETAIL_SHA256, complete=True,
            model='TEST ONLY: freshly observed current XBE gate union; no disc/archive build or inherited source pins',
            stack_image_size=XbeImage(final).image_size, stack_xbe_sha256=hashlib.sha256(final).hexdigest(),
            section_digests_verified=True, allocator_layout=pair.space.layout(final),
            source_sha256=sources, spans=spans, steps=recorder.steps,
            image_steps=['scorebug_runtime','season_2026'],
            xbe_only=True, new_disc_built=False, release_manifest=False, runtime_witnessed=False,
            scope='image_steps label the XBE components only; disc transport and archive writes were not run')
        observed = ReservationManifest(document,XbeImage(retail),source_root=ROOT)
        for owner, va, size in ((espn25.OWNER,espn25.XBE_SITE_VA,len(espn25.XBE_BEFORE)),
                                (trail.OWNER,trail.HOOK_VA,6)):
            self.assertTrue(observed.overlaps(va,va+size))
            self.assertEqual(observed.overlaps(va,va+size,exclude_owner=owner),[])
        from tests.nfl2k5_allocator_stack import manifest_for_allocated_union
        manifest_for_allocated_union(observed,retail,final)
        if output := os.environ.get('NFL2K5_PLAYBOOK_PAIR_MANIFEST'):
            path=Path(output).resolve()
            self.assertTrue(path.is_relative_to((ROOT/'.scratch').resolve()))
            path.write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
        print(f'Observed {len(recorder.steps)} XBE transactions and {len(spans)} reservations; no disc built')


if __name__=='__main__':
    unittest.main()
