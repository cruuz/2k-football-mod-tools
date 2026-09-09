"""Standalone strict owner, PLAY writer and neighbor-composition regressions."""
from pathlib import Path
import hashlib
import itertools
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_deep_zone as patch, nfl2k5_deep_zone_bail as bail
from mod_editor.core import nfl2k5_zone_drop as drop, nfl2k5_coverage_trail as trail
from mod_editor.core import nfl2k5_qb_spy_runtime as spy, nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit
from tests.mod_editor.test_nfl2k5_screen_hooks_unicorn import atl_resource


class PublicTests(unittest.TestCase):
    def test_budget_captions_and_experimental_capability(self):
        self.assertTrue(all(len(c)<=60 for c in patch.BUILD_CAPTIONS))
        for word in ("Retail","Patch","EXPERIMENTAL","UNWITNESSED"):
            self.assertIn(word,patch.HELP_TEXT)
        budget=json.loads((ROOT/'tests/fixtures/nfl2k5_allocator_beta62_requests.json').read_text())
        for row in patch.REQUESTS:self.assertIn(list(row),budget)
        from mod_editor.capabilities import validate_registry as registry
        cap=json.loads((ROOT/'docs/mod_editor/nfl2k5_deep_zone_capability.json').read_text())
        document=json.loads(registry.DEFAULT_REGISTRY.read_text())
        document['capabilities']=sorted([c for c in document['capabilities'] if c['id']!=cap['id']]+[cap],key=lambda c:c['id'])
        registry.validate_data(document,check_files=False)
        for path in cap['evidence']+[cap['backend']['module']]:registry._local_path(path,'deep-zone')
        self.assertEqual(registry._command_module(cap['backend']['command'],'backend'),cap['backend']['module'])
        registry._local_path(registry._command_module(cap['validation_command'],'validation'),'deep-zone')


class OwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.requests = patch.REQUESTS+drop.REQUESTS+trail.REQUESTS+spy.REQUESTS
        cls.seed = space.apply(cls.retail, cls.requests, scaleout=True)[0]
        cls.patched = patch.apply(cls.seed)[0]

    def test_variants_seals_replay_and_explicit_settings(self):
        for f, b in ((True, False), (False, True), (True, True)):
            with self.subTest(facing=f, bail=b):
                result, receipt = patch.apply(self.seed, facing=f, bail=b)
                self.assertEqual(patch.status(result), 'applied')
                self.assertEqual(patch.apply(result)[0], result)
                self.assertEqual(patch.read_settings(result)['facing'], f)
                self.assertFalse(receipt['runtime_witnessed'])
                self.assertTrue(receipt['experimental'])
                self.assertTrue(all(not v for v in receipt['presets'].values()))
                self.assertEqual(len(result), space.SCALE_FILE_SIZE)
                self.assertEqual(patch.apply(result, facing=f, bail=b)[1]['changed_bytes'], 0)
                with self.assertRaises(ValueError):
                    patch.apply(result, facing=not f, bail=not b)
        for kwargs in (dict(facing=False,bail=False), dict(facing=1), dict(bail='yes')):
            with self.assertRaises(ValueError): patch.apply(self.seed, **kwargs)
        self.assertEqual(patch.status(self.retail), 'retail')
        self.assertEqual(patch.status(b'XBEH'), 'foreign')

    def test_all_24_neighbor_orders_and_another_allocation_union(self):
        owners = (patch, drop, trail, spy)
        digest = None
        for order in itertools.permutations(owners):
            result = self.seed
            for m in order: result = m.apply(result)[0]
            for m in owners:
                self.assertEqual(m.status(result), 'applied', m.OWNER)
                self.assertEqual(m.apply(result)[0], result)
            digest = digest or hashlib.sha256(result).digest()
            self.assertEqual(hashlib.sha256(result).digest(), digest)
        # A separate owner set exercises every absolute and relative relocation.
        solo = patch.apply(self.retail)[0]
        self.assertNotEqual(patch.allocations(solo)['code']['va'], patch.allocations(self.patched)['code']['va'])
        self.assertEqual(patch.status(solo), 'applied')

    def test_every_hook_and_dependency_byte_refuses_before_mutation(self):
        image = XbeImage(self.patched)
        points = {va+i for va, old in patch.HOOKS.values() for i in range(len(old))}
        points.update(va+size-1 for va,size,_ in patch.GUARDS)
        for va in sorted(points):
            with self.subTest(va=hex(va)):
                bad = repin_edit(self.patched, va, bytes([image.read(va,1)[0]^1]))
                digest = hashlib.sha256(bad).digest()
                self.assertEqual(patch.status(bad), 'foreign')
                with self.assertRaises(ValueError): patch.apply(bad)
                self.assertEqual(hashlib.sha256(bad).digest(), digest)

    def test_exact_detours_without_code_or_with_resealed_foreign_code_refuse_spy(self):
        places = patch.allocations(self.seed)
        sites = patch.sites(places['code']['va'])
        forged = patch.rdata.apply(self.seed, sites, patch.OWNER)[0]
        self.assertEqual(space.status(forged), 'applied')
        self.assertEqual(patch.status(forged), 'foreign')
        self.assertEqual(spy.status(forged), 'foreign')
        raw = XbeImage(self.patched).read(places['code']['va'], patch.CODE_SIZE)
        for offset in (0, patch.assembly.LABELS['config'], patch.CODE_SIZE-1):
            content=bytearray(raw); content[offset]^=2
            bad=space.install_code(self.seed,patch.OWNER,bytes(content))[0]
            bad=patch.rdata.apply(bad,sites,patch.OWNER)[0]
            self.assertEqual(space.status(bad),'applied')
            for owner in (patch,spy):
                self.assertEqual(owner.status(bad),'foreign')
                with self.assertRaises(ValueError):owner.apply(bad)
        self.assertEqual(patch.status(repin_edit(self.patched,places['data']['va'],b'\1')),'foreign')

    def test_resealed_foreign_callback_or_spy_body_refuses_both_owners(self):
        joint=spy.apply(self.patched)[0]
        for va in (0x1A5796,0x1A5096,0x1A42FF,0x1ADF90):
            old=XbeImage(joint).read(va,1)
            bad=repin_edit(joint,va,bytes([old[0]^1]))
            self.assertEqual(patch.status(bad),'foreign')
            self.assertEqual(spy.status(bad),'foreign')
        places=spy.allocations(self.seed)
        out=patch.apply(self.seed)[0]
        content=bytearray(spy.code_for(places['code']['va'],places['data']['va'],places['read_only']['va']))
        content[0]^=1
        out=space.install_code(out,spy.OWNER,bytes(content))[0]
        out=space.install_read_only(out,spy.OWNER,spy.compile_intent_table()[0])[0]
        out=patch.rdata.apply(out,spy.sites(places['code']['va']),spy.OWNER)[0]
        self.assertEqual(space.status(out),'applied')
        self.assertEqual(patch.status(out),'foreign')

    def test_partial_allocation_refuses_and_no_cave_capacity_is_borrowed(self):
        wrong=space.apply(self.retail,patch.REQUESTS[:1],scaleout=True)[0]
        self.assertEqual(patch.status(wrong),'foreign')
        with self.assertRaises(ValueError):patch.apply(wrong)
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder=Recorder(self.retail)
        out,receipt=patch.apply(self.retail)
        recorder.observe(patch,'apply',self.retail,out,receipt)
        spans=recorder.finish(out)
        for va,old in patch.HOOKS.values():
            self.assertTrue(any(int(s['start'],0)<=va and va+len(old)<=int(s['end'],0)
                                and s['owner']==patch.OWNER for s in spans))
        self.assertLessEqual(len(patch.assembly.CODE), patch.CODE_SIZE)
        self.assertLessEqual(patch.RECORD_COUNT*patch.RECORD_SIZE,patch.DATA_SIZE)

    @unittest.skipUnless(shutil.which('as') and sys.platform != 'darwin', 'GNU as absent; generated source reproducibility check unavailable')
    def test_assembly_reproduces_and_cli_never_overwrites(self):
        subprocess.run([sys.executable,str(ROOT/'tools/nfl2k5_deep_zone_assemble.py'),'--check'],check=True,capture_output=True)
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory).resolve()/'default.xbe';target=source.with_name('patched.xbe')
            source.write_bytes(self.retail)
            argv=[sys.executable,'-m','mod_editor.core.nfl2k5_deep_zone','apply',str(source),'--output',str(target),'--tier','bail']
            run=subprocess.run(argv,capture_output=True,text=True,cwd=ROOT)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertFalse(json.loads(run.stdout)['facing'])
            before=target.read_bytes()
            self.assertEqual(subprocess.run(argv,capture_output=True,cwd=ROOT).returncode,2)
            self.assertEqual(target.read_bytes(),before)
            self.assertEqual(source.read_bytes(),self.retail)


class BailWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resource=atl_resource()
        cls.kwargs=dict(formation_index=22,front_play_index=1,coverage_play_index=13)

    def test_fixed_span_shared_node_isolation_exact_receipt_and_replay(self):
        result,receipt=bail.apply(self.resource,**self.kwargs)
        self.assertEqual(len(result),len(self.resource))
        self.assertEqual(receipt['corner_slots'],[9,10])
        self.assertEqual(receipt['result_sha256'],hashlib.sha256(result).hexdigest())
        self.assertEqual(bail.apply(result,**self.kwargs)[0],result)
        before=lib.play_chains(self.resource[32:],13)[1]
        after=lib.play_chains(result[32:],13)[1]
        for slot in range(11):
            if slot in (9,10):
                self.assertEqual(before[slot][1][1:],after[slot][1][1:])
                n=lib.exact_play_chains(result[32:],13)[slot][0]
                self.assertEqual((n[0],n[1][0],n[1][3]),(0x1B,1,0))
            else:self.assertEqual(before[slot],after[slot])
        book=bail.parse_playbook_resource(self.resource,asset_id='bail')
        for p in book.plays:
            if p.index!=13:
                self.assertEqual(lib.play_chains(self.resource[32:],p.index),lib.play_chains(result[32:],p.index))
        self.assertEqual(sum(a!=b for a,b in zip(self.resource,result)),receipt['changed_bytes'])

    def test_bad_selection_nondefense_and_non_resource_refuse(self):
        for r,kw in ((b'PLAY',self.kwargs),(self.resource,{**self.kwargs,'front_play_index':9999}),
                     (self.resource,{**self.kwargs,'formation_index':0}),
                     (self.resource,{**self.kwargs,'coverage_play_index':0}),
                     (self.resource,{**self.kwargs,'formation_index':True})):
            with self.subTest(kwargs=kw):
                with self.assertRaises(ValueError):bail.apply(r,**kw)


if __name__=='__main__':unittest.main()
