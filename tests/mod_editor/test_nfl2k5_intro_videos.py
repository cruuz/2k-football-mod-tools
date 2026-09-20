"""Boot movie cut: exact scope, native paths, transactional shrink and refusals."""
from pathlib import Path
from dataclasses import replace
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_intro_videos as cut, nfl2k5_crib_reclaim as crib
from mod_editor.core import nfl2k5_music_archive as archive, platform_compat as io
from mod_editor.core import mod_build, nfl2k5_build_settings as settings
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_movie_native import MovieMachine
from tests.nfl2k5_xiso_fixture import SyntheticXiso
from tools.nfl_outer import parse_archive, read_entry_range
from tools.nfl2k5_movie_inventory import NAMES


class SettingsTests(unittest.TestCase):
    def test_off_in_all_presets_and_saved_project_roundtrip(self):
        self.assertFalse(mod_build.BuildPlan('', '').trim_intro_videos)
        for key in mod_build.PRESETS:
            p = mod_build.BuildPlan('', '', trim_intro_videos=True)
            p = mod_build.apply_preset(p, key)
            self.assertFalse(p.trim_intro_videos, key)
        p = mod_build.BuildPlan('source.iso', 'output.iso', trim_intro_videos=True)
        restored = settings.to_plan(settings.from_plan(p), 'new.iso', 'out.iso')
        self.assertTrue(restored.trim_intro_videos)
        self.assertFalse(restored.crib_reclaim)
        with self.assertRaises(ValueError):
            settings.build_settings({'trim_intro_videos': 1})

    def test_combined_archive_shrink_refuses_before_build_copy(self):
        plan = mod_build.BuildPlan('source.iso','output.iso',trim_intro_videos=True,crib_reclaim=True)
        self.assertIn('final-pack capacity',mod_build.validate_plan(plan)[0])



@unittest.skipUnless(XBE.is_file(), 'pinned USA retail default.xbe is absent')
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('retail XBE differs from USA evidence pin')

    def test_guarded_idempotent_patch_preserves_all_shared_consumers(self):
        patched, receipt = cut.apply(self.retail)
        self.assertEqual(cut.apply(patched)[0], patched)
        self.assertEqual(cut.status(patched), 'applied')
        self.assertEqual(receipt['disc_bytes_reclaimed'], 0)
        self.assertEqual(cut.REQUESTS, ())
        im, original = XbeImage(patched), XbeImage(self.retail)
        for va, n in ((0x178150,0x573), (0x272a60,0x15c), (0x3634b0,0x6e), (0x4e9720,48)):
            self.assertEqual(im.read(va,n), original.read(va,n))
        allowed = set(range(im.offset(0x74bbb),im.offset(0x74bbb)+5))
        for s in cut._sections(patched):
            self.assertEqual(s.stored_digest,cut.section_digest(patched,s))
            allowed.update(range(s.header_offset+36,s.header_offset+56))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(patched,self.retail)) if a!=b))
        for va in (0x74bbb,0x74bce,0x4e9738,0x1781c5):
            bad = bytearray(self.retail); bad[original.offset(va)] ^= 1
            self.assertEqual(cut.status(bytes(bad)), 'foreign')
            with self.assertRaises(ValueError):cut.apply(bytes(bad))
        self.assertEqual(cut.apply(crib.apply(self.retail)[0])[0], crib.apply(patched)[0])

    def test_compares_new_hook_against_manifest_and_composed_stack(self):
        from mod_editor.core.nfl2k5_cave_oracle import ReservationManifest
        from tests import nfl2k5_allocator_stack as stack
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import OWNERS, prerequisites
        manifest=ReservationManifest.load(ROOT/'data/nfl2k5_cave_reservations.json',XbeImage(self.retail))
        self.assertEqual(manifest.overlaps(0x74bbb,0x74bc0),[])
        seed,_=stack.space.apply(prerequisites(self.retail),stack.REQUESTS,scaleout=True)
        for label,owner in OWNERS:
            with self.subTest(owner=label):
                first=cut.apply(owner.apply(seed)[0])[0]
                second=owner.apply(cut.apply(seed)[0])[0]
                self.assertEqual(first,second)
                self.assertEqual(cut.status(first),'applied')
                self.assertEqual(owner.status(first),'applied')

    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        entries = [(i, bytes([i % 251]) * 2048) for i in range(4323)]
        movies = []
        for i, name, *_ in cut.MOVIES:
            raw = bytes([i % 251]) * 6144
            entries[i] = (zlib.crc32(name.upper().encode('utf-16le')), raw)
            movies.append((i,name,len(raw),hashlib.sha256(raw).hexdigest()))
        patch = mock.patch.object(cut,'MOVIES',tuple(movies)); patch.start(); self.addCleanup(patch.stop)
        fx = SyntheticXiso(root,entries,pack_sizes=(0x90000,)*16,
                           pack_sectors=tuple(64+i*(0x90000//2048+1) for i in range(16)))
        fd = os.open(fx.path, os.O_RDWR | getattr(os,'O_BINARY',0))
        try:
            archive.write_named(fd,lambda n,at:io.pread(fd,n,at),0,'default.xbe',
                lambda n,at:self.retail[at:at+n],len(self.retail))
        finally:os.close(fd)
        return root,fx.path

    def test_streamed_shrink_verifies_every_retained_payload_and_replay(self):
        root,source = self.fixture(); output=root/'trim.iso'
        before = archive.file_hash(source)
        plan = cut.plan(source)
        self.assertEqual(plan['archive_bytes_reclaimed'],4*4096)
        self.assertEqual(plan['gamedata_append_credit'],0)
        receipt = cut.rebuild(source,output,expected_plan=plan)
        self.assertEqual(archive.file_hash(source),before)
        self.assertEqual(source.stat().st_size-output.stat().st_size,plan['disc_bytes_reclaimed'])
        self.assertEqual(receipt['verification']['outer_count'],4319)
        self.assertTrue(receipt['verification']['all_retained_outer_hashes_verified'])
        self.assertEqual(cut.image_status(output),'applied')
        replay = cut.rebuild(output,root/'replay.iso')
        self.assertEqual(replay['plan']['disc_bytes_reclaimed'],0)
        self.assertEqual(archive.file_hash(output),archive.file_hash(root/'replay.iso'))
        self.assertFalse(list(root.glob('.archive-*')))

    def test_foreign_payload_stale_plan_and_unpatched_tombstone_refuse(self):
        root,source = self.fixture()
        p=cut.plan(source)
        with self.assertRaisesRegex(ValueError,'stale'):
            cut.rebuild(source,root/'out.iso',expected_plan={**p,'source_bytes':1})
        with archive.Disc(source,descriptors=()) as disc:
            at=disc.entry_spans(disc.archive_entries[4293],0,1)[0].xiso_offset
        with source.open('r+b') as f:f.seek(at);f.write(b'!')
        with self.assertRaisesRegex(ValueError,'foreign Intro movie payload'):
            cut.rebuild(source,root/'out.iso')
        self.assertFalse((root/'out.iso').exists())

    def test_partial_movie_set_and_cut_without_skip_refuse(self):
        root,source=self.fixture()
        output=root/'cut.iso';cut.rebuild(source,output)
        fd=os.open(output,os.O_RDWR | getattr(os,'O_BINARY',0))
        try:
            archive.write_named(fd,lambda n,at:io.pread(fd,n,at),0,'default.xbe',
                lambda n,at:self.retail[at:at+n],len(self.retail))
        finally:os.close(fd)
        self.assertEqual(cut.image_status(output),'foreign')
        with self.assertRaisesRegex(ValueError,'consumer is enabled'):
            cut.rebuild(output,root/'unsafe.iso')
        with archive.Disc(source,descriptors=()) as disc:
            entry=disc.archive_entries[4293]
            at=disc.entry_spans(entry,0,entry.size)[0].xiso_offset
            table=disc.pack_extents['0'].byte_offset+156+4293*12
        with source.open('r+b') as f:
            f.seek(at);f.write(cut.TOMBSTONE)
            f.seek(table+4);f.write(struct.pack('<I',len(cut.TOMBSTONE)))
        self.assertEqual(cut.image_status(source),'foreign')

    def test_aliases_verification_failure_and_nonposix_publication(self):
        from tests.mod_editor.test_shipped_tools_posix_only import simulated_non_posix
        root,source = self.fixture(); before=archive.file_hash(source)
        with self.assertRaises(ValueError):cut.rebuild(source,source,overwrite=True)
        dest=root/'out.iso';dest.write_bytes(b'keep')
        with mock.patch.object(cut,'verify',side_effect=ValueError('forced verification failure')):
            with self.assertRaisesRegex(ValueError,'forced'):
                cut.rebuild(source,dest,overwrite=True)
        self.assertEqual(dest.read_bytes(),b'keep')
        with simulated_non_posix():cut.rebuild(source,root/'windows.iso')
        cut.rebuild(source,root/'posix.iso')
        self.assertEqual(archive.file_hash(root/'windows.iso'),archive.file_hash(root/'posix.iso'))
        self.assertEqual(archive.file_hash(source),before)
        self.assertFalse(list(root.glob('.archive-*')))

    def test_build_pipeline_reports_real_bytes_and_off_never_runs_trim(self):
        root,source=self.fixture()
        p=mod_build.BuildPlan(str(source),str(root/'built.iso'),trim_intro_videos=True,
                             camera=False,catch_slider=False,accel_ramp=False)
        # Synthetic archive has the true movie/XBE contract, no fabricated gameplay
        # resources. Bypass unrelated inspectors, keep Build's copy/publication and trim.
        with mock.patch.object(mod_build,'inspect',return_value={'container':'xiso'}), \
             mock.patch.object(mod_build.tt,'_check_installed_runtime_settings'), \
             mock.patch.object(mod_build.tt,'_naming_source_preflight'), \
             mock.patch.object(mod_build.tt,'_grown_status_fields',return_value={}):
            receipt=mod_build.build(p)
            self.assertEqual(receipt['intro_video_payload_bytes_freed'],4*4096)
            self.assertEqual(receipt['intro_video_disc_bytes_freed'],source.stat().st_size-(root/'built.iso').stat().st_size)
            self.assertEqual(receipt['intro_video_gamedata_memory_credit'],0)
            self.assertEqual(receipt['result']['trim_intro_videos'],'applied')
            with mock.patch.object(cut,'finish_output',side_effect=AssertionError('off must not trim')):
                off=mod_build.build(replace(p,target=str(root/'off.iso'),trim_intro_videos=False))
            self.assertNotIn('intro_video_disc_bytes_freed',off)
        self.assertFalse(list(root.glob('.studio-build-*')))


@unittest.skipUnless(HAVE_UC and XBE.is_file(),'Unicorn or pinned USA retail default.xbe is absent')
class NativeTests(unittest.TestCase):
    setUpClass = classmethod(RetailTests.setUpClass.__func__)
    def test_boot_loop_skip_and_retail_return_codes(self):
        for patched in (False,True):
            for result in (0,1,2):
                m=MovieMachine(cut.apply(self.retail)[0] if patched else self.retail)
                calls=[]
                m.stub(0x178150,lambda:(calls.append(m.string(m.reg('ECX'))),m.ret(result,pop=4)))
                m.call(0x74bbb,stop=0x74be3)
                self.assertEqual(calls,[] if patched else ['espn_videogames'] if result==2 else
                                 ['espn_videogames','vc','espn_game_sound','intro'])
                self.assertEqual(m.allocations_seen,[])

    def test_every_stream_missing_stub_and_native_header_allocation(self):
        path=XBE.parent/'vc_53450030/0'
        if not path.is_file():self.skipTest('retail packs are absent')
        a=parse_archive(path); rows=[]
        for i,name in enumerate(NAMES,4293):
            entry=a.entries[i]
            self.assertEqual(entry.name_id,zlib.crc32(name.upper().encode('utf-16le')))
            for kind in ('missing','marker','retail'):
                m=MovieMachine(self.retail)
                va=m.SAVE
                m.uc.mem_write(va,(name[:-4]+'\0').encode('utf-16le'))
                if kind=='marker':m.files[name]=lambda at,n:cut.TOMBSTONE[at:at+n]
                if kind=='retail':m.files[name]=lambda at,n,e=entry:read_entry_range(a,e,at,n) if at+n<=e.size else b''
                returned=m.call(0x178150,ecx=va,args=(0,),budget=100000)
                self.assertEqual(returned,0) # valid headers deliberately hit injected allocation failure
                self.assertEqual(m.get(0xaf5884),0xaf57c8)
                if kind=='retail':
                    self.assertEqual(len(m.allocations_seen),1)
                    self.assertGreater(m.allocations_seen[0],0)
                    if i < 4297:self.assertEqual(m.allocations_seen,[10171344])
                else:self.assertEqual(m.allocations_seen,[])
                self.assertLessEqual(len(m.reads),6)
                rows.append(dict(name=name,case=kind,return_code=returned,reads=m.reads,
                                 allocation_requests=m.allocations_seen,registered_contexts_after=0))
        destination=os.environ.get('NFL2K5_MOVIE_NATIVE_REPORT')
        if destination:Path(destination).write_bytes((json.dumps(rows,indent=2)+'\n').encode())

    def test_crib_23_choices_failure_cleanup_uses_retail_dispatch(self):
        for choice,(_,name,*_) in enumerate(crib.MOVIES):
            for kind in ('missing','marker'):
                m=MovieMachine(self.retail);pops=[]
                if kind=='marker':m.files[name]=lambda at,n:cut.TOMBSTONE[at:at+n]
                for va,pop in ((0x26da50,0),(0x2712f0,0),(0x2716a0,4)):
                    m.stub(va,lambda pop=pop:m.ret(pop=pop))
                m.stub(0x6e400,lambda:(pops.append(True),m.ret()))
                m.put(0xac8680,0);m.put(0xac8684,choice)
                m.call(0x272a60,args=(m.BODIES,))
                self.assertEqual(m.get(0xac8680),1)
                for _ in range(8):
                    m.call(0x38cd0)
                    if m.get(0xac8680)==6:break
                self.assertEqual(m.get(0xac8680),6)
                m.call(0x272a60,args=(m.BODIES,))
                self.assertEqual(pops,[True])
                self.assertEqual(m.allocations_seen,[])
                self.assertEqual(m.get(0xaf5884),0xaf57c8)

    def test_native_controller_skip_gate_and_completion_cleanup(self):
        for button in (0,0x10,0x100):
            m=MovieMachine(self.retail)
            m.reg('ESP',m.STACK);m.reg('EBP',m.SAVE);m.reg('EBX',0);m.reg('EDI',0)
            m.put(m.STACK+0x1c,0x3f800000);m.put(m.SAVE+8,0)
            m.stub(0x39b50,lambda:m.ret(button))
            m.stub(0x39bb0,lambda:m.ret())
            m.uc.emu_start(0x1784f7,0x178534,count=1000)
            self.assertEqual(m.reg('EIP'),0x178534)
            self.assertEqual(m.reg('EDI'),int(bool(button)))
            self.assertEqual(m.get(m.STACK+0x48),int(bool(button)))
        # Enter the real completion block with a live-buffer sentinel. Stop at
        # the common return decision after native free and context close calls.
        m=MovieMachine(self.retail);freed=[]
        m.reg('ESP',m.STACK);m.reg('EBX',0)
        m.put(m.STACK+0x5c,m.BODIES)
        m.stub(0x48870,lambda:(freed.append(m.reg('ECX')),m.ret()))
        m.uc.emu_start(0x17867e,0x17869d,count=1000)
        self.assertEqual(m.reg('EIP'),0x17869d)
        self.assertEqual(freed,[m.BODIES])
        self.assertEqual(m.get(m.STACK+0x14),1)

if __name__=='__main__':unittest.main()
