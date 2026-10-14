from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from PIL import Image, ImageDraw
from mod_editor.core import nfl2k5_indicator_names as n


class AtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name)
        image=Image.new("RGBA",n.ATLAS,(255,255,255,0))
        draw=ImageDraw.Draw(image)
        glyphs={}
        for i,char in enumerate(n.CHARACTERS):
            if char==" ":
                glyphs[char]=dict(rect=[0,0,0,0],quad=[0,0,0,0],advance=4)
                continue
            x,y=i%8*32,i//8*24
            width=9 if char=="W" else 6
            draw.rectangle((x+1,y+1,x+width-2,y+4),fill=(255,255,255,255))
            glyphs[char]=dict(rect=[x,y,x+width,y+6],quad=[-1,3,width-1,9],advance=width-1)
        image.save(self.folder/"atlas.png")
        self.spec=dict(schema=n.SCHEMA,atlas=list(n.ATLAS),texture="atlas.png",placeholder=False,
                       provenance="synthetic test rectangles, not font artwork",cap_height=4,line_advance=17,
                       baseline=15,outline=1,glyphs=glyphs)
        self.write()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self):
        (self.folder/"metrics.json").write_text(json.dumps(self.spec),newline="\n")

    def test_font_metrics_aliases_outline_and_roundtrip(self):
        raw,receipt=n.compile_font(self.folder)
        tx,_=n._tools()
        ch=tx.parse_chunks(raw)[0]
        decoded,_=tx.decode_chunk(raw,ch)
        self.assertEqual(n._name(decoded),n.NAME)
        obj=20+struct.unpack_from("<I",decoded,20)[0]-1
        ranges=obj+8+struct.unpack_from("<I",decoded,obj+8)[0]-1
        records=ranges+4+struct.unpack_from("<I",decoded,ranges+4)[0]-1
        record=lambda c:decoded[records+(ord(c)-32)*96:records+(ord(c)-31)*96]
        self.assertEqual(record('a'),record('A'))
        self.assertNotEqual(record('W')[:4],record('I')[:4])
        for char in "ST. BROWN O'CONNELL SMITH-NJIGBA":
            self.assertGreater(struct.unpack_from('<I',record(char))[0],0)
        pixels=tx.unswizzle_2d(decoded[ch.system_bytes:ch.system_bytes+32768],256,128,1)
        self.assertIn(15,pixels)
        self.assertIn(30,pixels)
        self.assertFalse(receipt['placeholder'])
        compressed=n._compressed(raw)
        self.assertEqual(tx.decode_chunk(compressed,tx.parse_chunks(compressed)[0])[0],decoded)

    def test_reject_missing_apostrophe(self):
        del self.spec['glyphs']["'"]
        self.write()
        with self.assertRaisesRegex(ValueError,'40 required'):
            n.load_atlas(self.folder)

    def test_reject_overlap_and_nonfinite_metrics(self):
        self.spec['glyphs']['B']['rect']=self.spec['glyphs']['A']['rect']
        self.write()
        with self.assertRaisesRegex(ValueError,'overlapping'):
            n.load_atlas(self.folder)
        self.spec['glyphs']['A']['quad'][0]=float('nan')
        self.write()
        with self.assertRaisesRegex(ValueError,'invalid quad'):
            n.load_atlas(self.folder)

    def test_reject_ink_at_cell_edge(self):
        image=Image.open(self.folder/'atlas.png').copy()
        image.putpixel((0,0),(255,255,255,255))
        image.save(self.folder/'atlas.png')
        with self.assertRaisesRegex(ValueError,'transparent pixel'):
            n.load_atlas(self.folder)

    def test_initializer_abi_with_found_and_missing_resource(self):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESP,UC_X86_REG_EAX,UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_ESI
        for pointer in (0x200000,0):
            machine=Uc(UC_ARCH_X86,UC_MODE_32)
            machine.mem_map(0,0x1000000)
            machine.mem_write(n.HOOK,n.hook_bytes())
            machine.mem_write(0x449e0,b'\xc2\x04\x00')
            machine.reg_write(UC_X86_REG_ESP,0x900000)
            seen=[]
            def lookup(uc,address,size,user):
                if address!=0x449e0:return
                sp=uc.reg_read(UC_X86_REG_ESP)
                seen.append((uc.reg_read(UC_X86_REG_ECX),uc.reg_read(UC_X86_REG_EDX),struct.unpack('<I',uc.mem_read(sp+4,4))[0]))
                uc.reg_write(UC_X86_REG_EAX,pointer)
            machine.hook_add(UC_HOOK_CODE,lookup)
            machine.emu_start(n.HOOK,n.HOOK_END,count=100)
            self.assertEqual(seen,[(0,int.from_bytes(b'FONT','little'),n.NAME_VA)])
            self.assertEqual(machine.reg_read(UC_X86_REG_ESP),0x900000)
            self.assertEqual(machine.reg_read(UC_X86_REG_ESI),pointer)
            self.assertEqual(struct.unpack('<I',machine.mem_read(0xa94ea8,4))[0],pointer+0x40 if pointer else 0)
            self.assertEqual(bytes(machine.mem_read(0xa951d8,4)),bytes.fromhex('c0c0c0ff'))

    def test_repair_refuses_unknown_disc_before_writing(self):
        from tools.b77.nm1_repair import repair
        base=self.folder/'base.iso';target=self.folder/'copy.iso'
        base.write_bytes(b'unknown disc');target.write_bytes(b'unknown disc')
        with self.assertRaisesRegex(ValueError,'unknown complete base disc hash'):
            repair(base,target,self.folder)
        self.assertEqual(target.read_bytes(),b'unknown disc')

    def test_fixed_scene_span_replay_and_other_resources_unchanged(self):
        from mod_editor.core.nfl2k5_scorebug_sprite import MAGIC,MARKER_OFFSET
        body=bytearray(24448)
        struct.pack_into('<I',body,16,17)
        body[32:52]='score_bug\0'.encode('utf-16le')
        struct.pack_into('<I',body,MARKER_OFFSET,MAGIC)
        scene=struct.pack('<4s7I',b'SCNE',len(body),len(body),0,0,0,0,0)+body
        neighbor=struct.pack('<4s7I',b'TXTR',128,128,0,0,0,0,0)+bytes(128)
        hud=neighbor+scene+neighbor
        fixed,receipt=n.apply_hud(hud,self.folder)
        self.assertEqual(len(hud),len(fixed))
        self.assertEqual(n.canonical_hud(fixed),hud)
        self.assertEqual(fixed[:len(neighbor)],neighbor)
        self.assertEqual(fixed[-len(neighbor):],neighbor)
        self.assertTrue(receipt['scene_bytes_unchanged'])
        replay,again=n.apply_hud(fixed,self.folder)
        self.assertEqual(replay,fixed)
        self.assertEqual(again['changed_bytes'],0)
        self.spec['glyphs']['A']['advance']+=1
        self.write()
        with self.assertRaisesRegex(ValueError,'different atlas already installed'):
            n.apply_hud(fixed,self.folder)


if __name__=='__main__':
    unittest.main()
