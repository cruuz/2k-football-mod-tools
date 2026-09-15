"""Execute the authored mask leaves and every APF-3 native case on pinned images."""
from __future__ import annotations
import json,struct,unittest
from pathlib import Path
from tests.mod_editor import test_apf_playcall_research_native as previous
from tools.apf_playcall_research_probe import BOOK,MASTER,MANAGER,OUTPUT,GAME,STATE
from mod_editor.core import apf2k8_situation_mask as mask


def install(machine, policies):
    patch = mask.compile_patch(machine.image, policies)
    image = bytearray(machine.image)
    for address, value in patch.words:
        data = struct.pack('>I', value)
        machine.cpu.mem_write(address, data)
        image[address-mask.IMAGE_BASE:address-mask.IMAGE_BASE+4] = data
    machine.image = bytes(image)
    return patch


class MaskNativeTests(previous.NativePlaycallTests):
    """Inherited thirty cases use the actual two detours with an empty policy."""
    def machine(self, book=767, updated=False, policies=None, **state):
        m = super().machine(book, updated, **state)
        install(m, policies or {})
        return m

    def test_apf4_elsewhere_presence_name_isolation_and_normalization(self):
        for updated in (False,True):
            policies={'O-ManBlock':[[] for _ in range(12)]};policies['O-ManBlock'][8]=[14]
            for down,yards in ((3,3),(2,8),(1,10)):
                machine=self.machine(130,updated,policies=policies,down=down,yards=yards,goal_yards=50)
                machine.normalize()
                selected=machine.call(machine.va(0x848693F8),MANAGER,14,MASTER+0x44+6*16,0,0,bound=2000000)
                self.assertEqual((selected-MASTER-0x244)//184,14)
                self.assertEqual(bytes(machine.cpu.mem_read(mask.RECEIPT_START,48)),bytes(48))
            # Exact same formation contents under another book name do not
            # acquire the O-ManBlock policy, even in the excluded live key.
            from mod_editor.core.apf2k8_book_clone import clone_body
            from mod_editor.core import apf2k8_splb_writer as splb
            other=splb.parse_book(clone_body(self.books[130].body,'USER-o'),0)
            machine=self.machine(other,updated,policies=policies,down=3,yards=8,goal_yards=50)
            machine.normalize()
            selected=machine.call(machine.va(0x848693F8),MANAGER,14,MASTER+0x44+6*16,0,0,bound=2000000)
            self.assertEqual((selected-MASTER-0x244)//184,14)
            self.assertEqual(bytes(machine.cpu.mem_read(mask.RECEIPT_START,48)),bytes(48))
        print('PROVED formation 14 present in three other buckets and renamed USER book after native normalization, BASE/TU')

    def test_apf4_exact_image_data_and_owned_ranges(self):
        evidence=[]
        for image in (self.base,self.tu):
            if image is None:self.skipTest('Owned TU 1.1 image absent')
            audit=mask.audit_reservations(image)
            policies={'O-ManBlock':[[] for _ in range(12)]};policies['O-ManBlock'][8]=[14]
            patch=mask.compile_patch(image,policies)
            patched=bytearray(image)
            for address,word in patch.words:struct.pack_into('>I',patched,address-mask.IMAGE_BASE,word)
            self.assertEqual(mask.decode_data(bytes(patched[mask.DATA_START-mask.IMAGE_BASE:mask.DATA_LIMIT-mask.IMAGE_BASE])),policies)
            spans=sorted([(site-mask.IMAGE_BASE,site-mask.IMAGE_BASE+4) for site in mask.HOOKS[patch.profile.name]]+
                         [(mask.CODE_START-mask.IMAGE_BASE,mask.CODE_START-mask.IMAGE_BASE+len(mask.assemble(patch.profile)[0])),
                          (mask.DATA_START-mask.IMAGE_BASE,mask.DATA_LIMIT-mask.IMAGE_BASE),
                          (mask.RECEIPT_START-mask.IMAGE_BASE,mask.RECEIPT_LIMIT-mask.IMAGE_BASE)])
            cursor=0
            for start,end in spans:
                self.assertEqual(patched[cursor:start],image[cursor:start]);cursor=end
            self.assertEqual(patched[cursor:],image[cursor:])
            import hashlib
            evidence.append({'profile':patch.profile.name,'patched_flat_sha256':hashlib.sha256(patched).hexdigest(),
                             'receipt':patch.receipt,'audit':audit})
        import os
        if os.environ.get('APF4_RECEIPT'):
            (Path(__file__).resolve().parents[2]/'reports/b71_apf4/native-byte-receipt.json').write_bytes((json.dumps(evidence,indent=2)+'\n').encode())
        print('PROVED owned ranges and exact patched flat image hashes:',[(r['profile'],r['patched_flat_sha256']) for r in evidence])

    def test_apf4_key_trace_boundaries_and_special_bypasses(self):
        evidence=[]
        for updated in (False,True):
            for down in range(1,5):
                for yards in (0,1.999,2.001,6.999,7.001,100):
                    policies={'O-ManBlock':[[14] for _ in range(12)]}
                    m=self.machine(130,updated,policies=policies,down=down,yards=yards,goal_yards=50)
                    # Execute the real member selector with its ordinary category,
                    # then read the key actually used by the native filter.
                    m.call(m.va(0x848693F8),MANAGER,14,MASTER+0x44+6*16,0,0,bound=2000000)
                    ball=struct.unpack('>f',m.cpu.mem_read(STATE+0x18,4))[0]
                    target=struct.unpack('>f',m.cpu.mem_read(STATE+0x28,4))[0]
                    expected=mask.live_key(down,target-ball)
                    self.assertEqual(m.get(mask.RECEIPT_START+24),expected)
                    evidence.append({'tu':updated,'down':down,'yards':yards,'key':expected,'ball':ball,'target':target})
            for phase in (1,2,3,4):
                policies={'O-ManBlock':[[r.formation_index for r in self.books[130].records if r.populated and r.formation_index<151] for _ in range(12)]}
                baseline=previous.NativePlaycallTests.machine(self,130,updated,down=4,yards=1,goal_yards=30)
                changed=self.machine(130,updated,policies=policies,down=4,yards=1,goal_yards=30)
                for machine in (baseline,changed):
                    machine.put(GAME+(0x30 if updated else 0)+0x34,phase)
                    machine.call(machine.va(0x8486CE88),MANAGER,OUTPUT,stop=machine.va(0x8486D0CC),bound=2000000)
                self.assertEqual(bytes(baseline.cpu.mem_read(OUTPUT,32)),bytes(changed.cpu.mem_read(OUTPUT,32)))
                self.assertEqual(bytes(changed.cpu.mem_read(mask.RECEIPT_START,48)),bytes(48))
        import os
        if os.environ.get('APF4_RECEIPT'):
            (Path(__file__).resolve().parents[2]/'reports/b71_apf4/native-key-receipt.json').write_bytes((json.dumps(evidence,indent=2)+'\n').encode())
        print('PROVED live-key boundary traces:',len(evidence),'plus 8 untouched kick/try cases')

    def test_apf4_draws_are_local_and_never_empty(self):
        receipts=[]
        for updated in (False,True):
            for excluded in ([14], [2,14,24], [r.formation_index for r in self.books[130].records if r.populated and r.formation_index<151]):
                policies={'O-ManBlock':[[] for _ in range(12)]}
                policies['O-ManBlock'][8]=sorted(set(excluded))
                for down,yards in ((3,8),(3,3),(2,8)):
                    for fraction in (.01,.25,.5,.75,.99):
                        m=self.machine(130,updated,policies=policies,down=down,yards=yards,goal_yards=50,run_share=0,fraction=fraction)
                        traces=[]
                        for hook in mask.HOOKS['tu_1_1' if updated else 'base']:
                            m.observers[hook]=lambda z: traces.append({'pc':z.cpu.reg_read(z.r.UC_PPC_REG_PC),'down':z.get(STATE+4),'ball':z.get(STATE+0x18),'target':z.get(STATE+0x28),'book':bytes(z.cpu.mem_read(BOOK+0x30,56)).decode('utf-16-be').rstrip('\0')})
                        m.call(m.va(0x8486CE88),MANAGER,OUTPUT,stop=m.va(0x8486D0CC),bound=2000000)
                        call=tuple((m.get(OUTPUT+d)-MASTER-off)//stride for d,off,stride in ((0,0x44,16),(4,0x244,184),(12,0x80C4,100)))
                        stats=[struct.unpack('>6I',m.cpu.mem_read(mask.RECEIPT_START+i*24,24)) for i in range(2)]
                        self.assertTrue(0<=call[0]<28 and 0<=call[1]<163 and 0<=call[2]<586,call)
                        if down==3 and yards==8 and len(excluded)<=3:
                            self.assertNotIn(call[1],excluded,(call,stats))
                        if down==3 and yards==8 and len(excluded)>3:
                            self.assertEqual(stats[0][4],1,stats)
                            self.assertEqual(stats[1][4],1,stats)
                        if down!=3 or yards!=8:
                            self.assertEqual(stats,[(0,)*6]*2)
                        receipts.append(dict(profile='tu_1_1' if updated else 'base',excluded=excluded,down=down,yards=yards,fraction=fraction,call=call,stats=stats,traces=traces))
        target=Path(__file__).resolve().parents[2]/'reports/b71_apf4/native-mask-receipt.json'
        # Evidence output is opt-in; standalone CI never writes the repository.
        import os
        if os.environ.get('APF4_RECEIPT'):
            target.write_bytes((json.dumps(receipts,indent=2)+'\n').encode())
        print('PROVED APF4 local masks / two empty-draw fallbacks:',len(receipts))


if __name__=='__main__':unittest.main(verbosity=2)
