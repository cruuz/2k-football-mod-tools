"""PROVED OFFLINE: pc patch bytes, source pins, build gating and native projection."""
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_playcall_layout as pc
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from nfl2k5_playcall_projection import DEFAULT_XBE, DEFAULT_PACK, native_proof, scene_sources, measurements


def replace_at(payload, va, value):
    buf = bytearray(payload)
    off = owner.scene.layout.sbpos.va_to_off(payload,va)
    buf[off:off+len(value)] = value
    for s in _sections(buf):
        buf[s.header_offset+36:s.header_offset+56] = section_digest(buf,s)
    return bytes(buf)


@unittest.skipUnless(DEFAULT_XBE.is_file(), 'local USA retail XBE required')
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = DEFAULT_XBE.read_bytes()
        with mock.patch.dict(os.environ, {'NFL2K5_SCOREBUG_PLAYCALL':'sprite'}):
            cls.patched, cls.receipt = owner.apply(cls.retail)

    def setUp(self):
        p = mock.patch.dict(os.environ, {'NFL2K5_SCOREBUG_PLAYCALL':'sprite'})
        p.start(); self.addCleanup(p.stop)

    def test_exact_sites_and_idempotence(self):
        self.assertEqual(owner.status(self.retail), 'retail')
        self.assertEqual(owner.status(self.patched), 'applied')
        self.assertTrue(pc.valid(self.retail,applied=False))
        self.assertTrue(pc.valid(self.patched,applied=True))
        image = XbeImage(self.patched)
        code,data = owner.sites(self.patched)
        compiled,labels = owner.code_for(code['va'],data['va'])
        self.assertEqual(image.read(code['va'],owner.CODE_SIZE),compiled)
        hook = b'\xe8'+struct.pack('<i',labels[pc.HOOK_NAME]-pc.HOOK[0]-5)
        self.assertEqual(image.read(pc.HOOK[0],5),hook)
        for va,old,new,_ in pc.edits():
            self.assertEqual(XbeImage(self.retail).read(va,4),old)
            self.assertEqual(image.read(va,4),new)
        again,receipt = owner.apply(self.patched)
        self.assertEqual(again,self.patched)
        self.assertEqual(receipt['changed_bytes'],0)

    def test_every_source_guard_refuses_mutation(self):
        for va,size,_,label in pc.GUARDS:
            # Mutate the last byte to avoid the normalized hook/data operands.
            at = va+size-1
            old = XbeImage(self.retail).read(at,1)
            changed = replace_at(self.retail,at,bytes([old[0]^1]))
            with self.subTest(label=label):
                self.assertEqual(owner.status(changed),'foreign')
                with self.assertRaises(ValueError): owner.apply(changed)

    def test_each_data_word_and_hook_rejects_mixed_states(self):
        for va,old,new,label in pc.edits():
            with self.subTest(label=label,va=hex(va)):
                self.assertEqual(owner.status(replace_at(self.retail,va,new)),'foreign')
                self.assertEqual(owner.status(replace_at(self.patched,va,old)),'foreign')
        self.assertEqual(owner.status(replace_at(self.patched,*pc.HOOK)),'foreign')

    def test_build_option_off_does_not_call_owner_or_change_bytes(self):
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        with mock.patch.object(owner,'apply',wraps=owner.apply) as apply:
            unchanged,_ = tuning._apply_all(self.retail,None,catch_slider=False,scorebug_runtime=False)
            apply.assert_not_called()
        self.assertEqual(unchanged,self.retail)

    def test_build_option_on_installs_layout(self):
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        built,_ = tuning._apply_all(self.retail,None,catch_slider=False,scorebug_runtime=True)
        self.assertEqual(owner.status(built),'applied')
        self.assertTrue(pc.valid(built,applied=True))

    def test_retail_playcalling_escape_keeps_all_layout_bytes(self):
        with mock.patch.dict(os.environ, {'NFL2K5_SCOREBUG_PLAYCALL':'retail'}):
            result,_ = owner.apply(self.retail)
            self.assertEqual(owner.status(result),'applied')
            self.assertNotIn(pc.HOOK_NAME,owner.hooks())
            image = XbeImage(result)
            self.assertEqual(image.read(pc.HOOK[0],5),pc.HOOK[1])
            for va,old,_,_ in pc.edits(): self.assertEqual(image.read(va,4),old)
            self.assertEqual(owner.status(self.patched),'foreign')
        self.assertEqual(owner.status(result),'foreign')

    def test_code_budget_and_full_manifest_site_reservations(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        code,_ = owner.code_for(0x5100000,0x5200000)
        self.assertEqual((owner.CODE_SIZE,owner.DATA_SIZE,owner.REVISION),(5376,128,13))
        self.assertEqual(len(code.rstrip(b'\xcc')),5287)
        self.assertEqual(len(pc.code_for(0x5100000)),129)
        rec = Recorder(self.retail)
        rec.observe(owner,'apply',self.retail,self.patched,self.receipt)
        for va,size in [(pc.HOOK[0],5)]+[(va,4) for va,*_ in pc.edits()]:
            self.assertTrue(any(int(r['start'],0)==va and r['size']==size and r['owner']==owner.OWNER
                                for r in rec.spans),hex(va))

    @unittest.skipUnless((DEFAULT_PACK/'0').is_file(), 'local retail GAMEDATA required')
    def test_native_initializers_animation_cameras_and_viewports(self):
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(DEFAULT_PACK)
        result = native_proof(self.retail,scene_sources(DEFAULT_PACK))
        self.assertEqual(result['matrix_samples'],450)
        self.assertLess(result['max_matrix_error'],.0001)
        self.assertEqual(sum(len(s['nodes']) for s in result['scene_sources']),14)
        self.assertEqual(result['viewports'][0]['before'],result['viewports'][0]['after'])
        self.assertEqual(result['menu_target'][1],16.)

    def test_measured_clearance_respects_native_menu_clip_boundary(self):
        research = Path('/media/noah/Storage/.b76-research')
        for relative in (
            'main/witness/kr_candE/ari.jpg',
            'main/witness/kr_candE/det.jpg',
            'hx/lab-F-20260929-091218/s37-hou/attempt-01/screens/09-last-play.png',
            'hx/lab-20260929-072352/ari-kickoff/attempt-02/screens/toss-0131.3s.jpg',
        ):
            frame = research / relative
            if not frame.is_file():
                self.skipTest(f'Missing private witness frame: {frame}')
        result = measurements(research)
        for row in result['frames']:
            self.assertEqual((row['bar_top_weak'],row['bar_top_strong']),(569,570))
            self.assertGreaterEqual(row['projected_bar_gap'],4.)
        self.assertGreaterEqual(result['design']['selected_menu_clip_margin'],2.)
        self.assertLessEqual(pc.SHIFT,result['design']['max_shift_for_2px_menu_clip_margin'])
        # This explicitly records the limit: a uniform shift cannot clear the
        # raised timeout tab and retain the kickoff selector inside the viewport.
        self.assertGreater(result['design']['timeout_min_shift_for_1px_gap'],
                           result['design']['max_shift_for_2px_menu_clip_margin'])

    def test_tailcall_preserves_native_abi_flags_and_registers(self):
        from nfl2k5_scorebug_projection import StaticMachine
        m = StaticMachine(self.retail); m.record=False
        try:
            cave = 0x5100000
            m.uc.mem_map(cave,4096); m.uc.mem_write(cave,pc.code_for(cave))
            for glob,_,_ in pc.SCENES: m.put(glob,0)
            regs = dict(eax=0x12345678,ebx=0x10203040,esi=0x87654321,edi=0x98765432,
                        ebp=0x11223344,ecx=0xb719d0,edx=0x4f0e20,eflags=0x246)
            args = (0x4f0e10,0x4f0e00,0x4f0df0)
            snapshots = []
            for target in (0x2ba10,cave):
                m.run(target,args,**regs)
                snapshots.append(([m.uc.reg_read(getattr(m.x,'UC_X86_REG_'+n.upper())) for n in (*regs,'esp')],
                                  bytes(m.uc.mem_read(0xb719d0,0x2b0))))
            self.assertEqual(*snapshots)
        finally: m.close()

    def test_null_and_foreign_count_scenes_are_not_written(self):
        from nfl2k5_scorebug_projection import StaticMachine
        m = StaticMachine(self.retail); m.record=False
        try:
            cave = 0x5100000
            m.uc.mem_map(cave,4096); m.uc.mem_write(cave,pc.code_for(cave))
            for i,(glob,count,_) in enumerate(pc.SCENES):
                if i==0: m.put(glob,0); continue
                desc=m.alloc(128); m.put(glob,desc); m.put(desc+0x24,count+1 if i==1 else count)
                # A changed count must not dereference this unmapped pointer;
                # the other scene has a valid count but a null nodes pointer.
                m.put(desc+0x28,0xdeadbeef if i==1 else 0)
            m.run(cave,(0x4f0e10,0x4f0e00,0x4f0df0),ecx=0xb719d0,edx=0x4f0e20)
        finally: m.close()


if __name__=='__main__': unittest.main()
