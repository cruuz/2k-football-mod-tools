"""Native failure/completion tests for the presentation-pool exhaustion fix."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import gc
import hashlib
import importlib.util
import os
import struct
import tempfile
import unittest

from mod_editor.core import nfl2k5_resource_load_guard as guard
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_bump_strength as strength
try:  # the Unicorn harness for the native class; Unicorn is optional and that class skips without it
    from tests.mod_editor import resource_load_guard_probe as probe
except ImportError:
    probe = None
from mod_editor.core.nfl2k5_practice_squad import RETAIL_SHA256

XBE=Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION','/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)/default.xbe'


class BuildWiringTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('PyQt5'),'PyQt5 required')
    def test_gui_flag_roundtrip_and_source_gating(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui.build_panel_qt import BuildPanel
        app=QApplication.instance() or QApplication([])
        panel=BuildPanel()
        try:
            panel.apply_state({'resource_load_guard':'retail'})
            panel.resource_load_guard_check.setChecked(True)
            saved=panel.project_build_settings()
            self.assertTrue(saved['resource_load_guard'])
            panel.resource_load_guard_check.setChecked(False)
            panel.restore_project_build_settings(saved)
            self.assertTrue(panel.plan().resource_load_guard)
            panel.apply_state({'resource_load_guard':'applied'})
            self.assertFalse(panel.resource_load_guard_check.isChecked())
            self.assertFalse(panel.resource_load_guard_check.isEnabled())
        finally:
            panel.deleteLater()
            app.processEvents()

    def test_default_presets_and_persistence(self):
        plan=mod_build.BuildPlan(source=Path('default.xbe'),target=Path('out.xbe'))
        self.assertFalse(plan.resource_load_guard)
        self.assertFalse(plan.wants_xbe_patch())
        for preset in mod_build.PRESETS:
            self.assertTrue(mod_build.apply_preset(plan,preset).resource_load_guard)
        self.assertTrue(mod_build.BuildPlan(source=plan.source,target=plan.target,resource_load_guard=True).wants_xbe_patch())
        self.assertIn('resource_load_guard',settings.FEATURE_KEYS)
        self.assertTrue(mod_build.availability()['resource_load_guard'])


@unittest.skipUnless(probe is not None and XBE.is_file() and importlib.util.find_spec('unicorn'),'pinned retail XBE, Unicorn and the POSIX native harness required')
class GuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail=XBE.read_bytes()
        assert hashlib.sha256(cls.retail).hexdigest()==RETAIL_SHA256
        cls.patched,cls.receipt=guard.apply(cls.retail)

    def machine(self,payload):
        import unicorn as uni
        p=probe.Probe()
        p.uc=uni.Uc(uni.UC_ARCH_X86,uni.UC_MODE_32)
        p.uc.mem_map(0x10000,0x1510000-0x10000)
        for sec in strength._sections(payload):
            p.uc.mem_write(sec.virtual_address,payload[sec.raw_offset:sec.raw_offset+sec.raw_size])
        for address,size in ((p.BASE,0x200000),(0x03000000,0x10000),(p.STOP,0x1000),(p.MAIN,p.MAIN_SIZE)):
            p.uc.mem_map(address,size)
        self.addCleanup(lambda:self.close(p))
        return p

    @staticmethod
    def close(p):
        p.uc=None
        gc.collect()

    def test_exact_writer_readback_idempotence_and_digest(self):
        self.assertEqual(guard.status(self.retail),'retail')
        self.assertEqual(guard.verify(self.patched)['status'],'applied')
        again,receipt=guard.apply(self.patched)
        self.assertEqual(again,self.patched)
        self.assertEqual(receipt['changed_bytes'],0)
        spans=[]
        for _,va,before,_ in guard.SITES:
            off=rdata.offset_of(self.retail,va);spans.append((off,off+len(before)))
        for sec in strength._sections(self.patched):
            self.assertEqual(self.patched[sec.header_offset+36:sec.header_offset+56],strength.section_digest(self.patched,sec))
            spans.append((sec.header_offset+36,sec.header_offset+56))
        changed=[i for i,(a,b) in enumerate(zip(self.retail,self.patched)) if a!=b]
        self.assertEqual(len(self.retail),len(self.patched))
        self.assertTrue(all(any(lo<=i<hi for lo,hi in spans) for i in changed))

    def test_mixed_and_corrupt_prerequisites_are_refused(self):
        for name,va,before,after in guard.SITES:
            data=bytearray(self.retail);off=rdata.offset_of(data,va)
            data[off:off+len(after)]=after
            self.assertEqual(guard.status(bytes(data)),'foreign',name)
            with self.assertRaises(ValueError):guard.apply(bytes(data))
        for va,_,_ in guard.GUARDS:
            data=bytearray(self.patched);data[rdata.offset_of(data,va)]^=1
            self.assertEqual(guard.status(bytes(data)),'foreign')
            with self.assertRaises(ValueError):guard.apply(bytes(data))

    def test_dispatcher_option_off_on_and_copy_writer(self):
        unchanged,_=tt._apply_all(self.retail,None,catch_slider=False,resource_load_guard=False)
        self.assertEqual(unchanged,self.retail)
        patched,receipt=tt._apply_all(self.retail,None,catch_slider=False,resource_load_guard=True)
        self.assertEqual(patched,self.patched)
        self.assertIn('resource_load_guard_patch',receipt)
        with tempfile.TemporaryDirectory() as tmp:
            source,target=Path(tmp)/'in.xbe',Path(tmp)/'out.xbe'
            source.write_bytes(self.retail)
            receipt=tt.write_xbe_copy(source,target,resource_load_guard=True)
            self.assertEqual(target.read_bytes(),self.patched)
            self.assertEqual(source.read_bytes(),self.retail)
            self.assertEqual(tt.read_xbe(target)['resource_load_guard'],'applied')
            self.assertEqual(mod_build.inspect(target)['resource_load_guard'],'applied')

    def test_playbook_pair_composes_in_either_order_and_keeps_its_mode_call(self):
        from mod_editor.core import nfl2k5_playbook_pair as pair
        paired,_=pair.apply(self.retail)
        pair_first,_=guard.apply(paired)
        guard_first,_=pair.apply(self.patched)
        self.assertEqual(pair_first,guard_first)
        self.assertEqual(pair.status(pair_first),'applied')
        self.assertEqual(guard.status(pair_first),'applied')
        offset=rdata.offset_of(paired,0x166617)
        self.assertEqual(pair_first[offset:offset+5],paired[offset:offset+5])
        composed,_=tt._apply_all(self.retail,None,catch_slider=False,
                                resource_load_guard=True,playbook_pair=True)
        self.assertEqual(pair.status(composed),'applied')
        self.assertEqual(guard.status(composed),'applied')
        corrupted=bytearray(pair_first)
        corrupted[rdata.offset_of(corrupted,0x166665)]^=1
        self.assertEqual(pair.status(bytes(corrupted)),'foreign')
        self.assertEqual(guard.status(bytes(corrupted)),'foreign')

    def test_all_eight_loaders_reject_full_pool_and_preserve_success_arguments(self):
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESP,UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP
        for name,va,_,_ in guard.SITES[:-1]:
            va=0x166610 if name=="PLAY" else va
            for capacity in (0,18176,83712,214784):
                results=[]
                for fixed,data in ((False,self.retail),(True,self.patched)):
                    p=self.machine(data)
                    p.call(0x48640,ecx=probe.HEAP_B,edx=p.MAIN,args=(capacity,))
                    p.put(0xB12034,probe.HEAP_B)
                    p.put(0xB9C198,0) # PLAY's allocating branch
                    header,request=p.BASE,p.BASE+0x100
                    p.uc.mem_write(header,struct.pack('<8I',int.from_bytes(name.encode(),'little'),73680,73664 if name=="_bin" else 0,0,0,0,0,0))
                    p.put(request,probe.OFFSET)
                    reads=[]
                    def read(*_):
                        sp=p.uc.reg_read(UC_X86_REG_ESP)
                        reads.append((p.uc.reg_read(UC_X86_REG_ECX),p.uc.reg_read(UC_X86_REG_EDX),
                                      bytes(p.uc.mem_read(sp+4,20))))
                        p._return(1,20)
                    h=p.uc.hook_add(UC_HOOK_CODE,read,begin=0x48FF0,end=0x48FF0)
                    if name=='_bin' and not fixed and capacity<73856:
                        with self.assertRaisesRegex(AssertionError,'fault at 0x45db1'):
                            p.call(va,ecx=request,edx=header)
                        p.uc.hook_del(h)
                        results.append('retail NULL header write')
                        self.close(p)
                        continue
                    result=p.call(va,ecx=request,edx=header)
                    p.uc.hook_del(h)
                    self.assertEqual([p.uc.reg_read(r) for r in (UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP)],
                                     [0x11111111,0x22222222,0x33333333,0x44444444])
                    self.assertEqual(p.uc.reg_read(UC_X86_REG_ESP),p.STACK+4)
                    if fixed and capacity<73856:
                        self.assertEqual((result,reads),(0,[]))
                    else:
                        self.assertEqual(len(reads),1)
                        self.assertEqual(bool(reads[0][1]),capacity>=73856)
                    results.append(reads)
                    self.close(p)
                if capacity>=73856:self.assertEqual(*results)

    def test_empty_heap_does_not_write_its_boundary_and_nonempty_heaps_match(self):
        for capacity in (0,128,256,18176,83712,214784):
            states=[]
            returns=[]
            for data in (self.retail,self.patched):
                p=self.machine(data)
                p.uc.mem_write(p.MAIN,b'\xA5'*256)
                returns.append(p.call(0x48640,ecx=probe.HEAP_B,edx=p.MAIN,args=(capacity,)))
                states.append((bytes(p.uc.mem_read(probe.HEAP_B,0xA0)),bytes(p.uc.mem_read(p.MAIN,max(256,capacity)))))
                if data==self.patched and capacity==0:
                    self.assertEqual(states[-1][1],b'\xA5'*256)
                    self.assertEqual(p.call(0x48700,ecx=probe.HEAP_B,edx=73680),0)
                    self.assertEqual(states[-1][0][8:0x88],bytes(128))
                self.close(p)
            if capacity:self.assertEqual(*states)
            self.assertEqual(*returns)

    def test_all_failed_handlers_complete_the_native_resource_context(self):
        for name,va,_,_ in guard.SITES[:-1]:
            va=0x166610 if name=="PLAY" else va
            p=self.machine(self.patched)
            p.main_heap(0x20000)
            p.call(0x48640,ecx=probe.HEAP_B,edx=p.BASE+0x100000,args=(18176,))
            p.put(0xBB75DC,1)
            p.put(0xE5FF80,4)
            entry=struct.pack('<8I',int.from_bytes(name.encode(),'little'),73680,73664,0,0,0,0,0)+bytes(73680)
            result=p.stream_intro(entry,loader_va=va)
            self.assertEqual(result['reads'],[],name)
            self.assertTrue(result['ready'],name)
            self.assertEqual(result['loading'],0,name)
            self.close(p)

    def test_fallback_heap_and_special_loader_branches_keep_retail_reads(self):
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_EDX,UC_X86_REG_ESP
        # CACR's high-end allocator and _bin's compressed staging address are distinct branches.
        for name,va,_,_ in (r for r in guard.SITES if r[0] in ('CACR','_bin','DRCT')):
            rows=[]
            for data in (self.retail,self.patched):
                p=self.machine(data)
                p.main_heap(214784)
                p.call(0x48640,ecx=probe.HEAP_B,edx=p.BASE+0x100000,args=(18176,))
                p.put(probe.HEAP_B+0x8c,probe.MAIN_HEAP)
                p.put(0xB12034,probe.HEAP_B)
                header,req=p.BASE,p.BASE+0x100
                p.uc.mem_write(header,struct.pack('<8I',int.from_bytes(name.encode(),'little'),
                                4096 if name=='_bin' else 73680,65536,0,
                                0xfeedbeef if name=='_bin' else 0,8128,0,0))
                p.put(req,probe.OFFSET)
                if name=='CACR':
                    p.put(0xB09578,p.BASE+0x200)
                    p.put(p.BASE+0x210,p.BASE+0x300)
                    p.put(p.BASE+0x388,1)
                reads=[]
                def read(*_):
                    sp=p.uc.reg_read(UC_X86_REG_ESP)
                    reads.append((p.uc.reg_read(UC_X86_REG_EDX),bytes(p.uc.mem_read(sp+4,20))))
                    p._return(1,20)
                h=p.uc.hook_add(UC_HOOK_CODE,read,begin=0x48FF0,end=0x48FF0)
                p.call(va,ecx=req,edx=header)
                p.uc.hook_del(h)
                self.assertEqual(len(reads),1)
                self.assertTrue(reads[0][0])
                rows.append(reads)
                self.close(p)
            self.assertEqual(*rows)

    def test_play_borrowed_buffers_keep_the_same_native_route(self):
        # The heap branch was repaired; mode 1 and mode 2 use existing playbook buffers.
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_EDX
        for mode in (1,2):
            outputs=[]
            for data in (self.retail,self.patched):
                p=self.machine(data);reads=[]
                p.put(p.BASE+4,32)
                h=p.uc.hook_add(UC_HOOK_CODE,lambda *_:p._return(mode),begin=0xE99C0,end=0xE99C0)
                def read(*_):
                    reads.append(p.uc.reg_read(UC_X86_REG_EDX));p._return(1,20)
                h2=p.uc.hook_add(UC_HOOK_CODE,read,begin=0x48FF0,end=0x48FF0)
                p.call(0x166610,ecx=p.BASE+0x100,edx=p.BASE)
                outputs.append(reads)
                p.uc.hook_del(h);p.uc.hook_del(h2);self.close(p)
            self.assertEqual(*outputs)
            self.assertEqual(outputs[0],[0xB75A40+(mode-1)*0x13390])


if __name__=='__main__':unittest.main()
