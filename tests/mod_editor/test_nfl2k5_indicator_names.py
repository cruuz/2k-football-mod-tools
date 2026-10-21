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

    def test_native_human_label_flag_all_ports_options_and_expired_timers(self):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
        from unicorn.x86_const import (UC_X86_REG_ESI,UC_X86_REG_ECX,UC_X86_REG_ESP,
                                       UC_X86_REG_EDI,UC_X86_REG_EBX)
        machine=Uc(UC_ARCH_X86,UC_MODE_32)
        machine.mem_map(0,0x1000000)
        machine.mem_write(n.CONTROL,n.control_bytes())
        entity,controller=0x200000,0x210000
        machine.reg_write(UC_X86_REG_ESI,entity)
        machine.reg_write(UC_X86_REG_ESP,0x900000)
        machine.reg_write(UC_X86_REG_EDI,0x12345678)
        machine.reg_write(UC_X86_REG_EBX,0)
        seen=0
        for port in (0,1,2,3,4,0xffffffff):
            for option in (0,1,2,3,0xffffffff):
                for timer in (-100.0,0.0,0.5,2.0):
                    machine.mem_write(entity+0x0c,struct.pack('<I',controller))
                    machine.mem_write(entity+0x44,struct.pack('<f',timer))
                    machine.mem_write(controller,struct.pack('<I',port))
                    machine.mem_write(0xe5ff90,struct.pack('<I',option))
                    machine.mem_write(0xe5ff80,struct.pack('<I',4))
                    machine.mem_write(0xb616c0,struct.pack('<I',16))
                    before=bytes(machine.mem_read(entity,0x50))
                    machine.reg_write(UC_X86_REG_ECX,0xdeadbeef)
                    machine.emu_start(n.CONTROL,n.CONTROL_END,count=100)
                    self.assertEqual(machine.reg_read(UC_X86_REG_ECX),int(port<4 and option<2))
                    self.assertEqual(bytes(machine.mem_read(entity,0x50)),before)
                    self.assertEqual(machine.reg_read(UC_X86_REG_EDI),0x12345678)
                    self.assertEqual(machine.reg_read(UC_X86_REG_EBX),0)
                    self.assertEqual(machine.reg_read(UC_X86_REG_ESP),0x900000)
                    seen+=1
        self.assertEqual(seen,120)
        # Reject null controllers and retain the native non-field/display gates.
        for pointer,game,display in ((0,16,4),(controller,2,4),(controller,3,4),(controller,16,3)):
            machine.mem_write(entity+0x0c,struct.pack('<I',pointer))
            machine.mem_write(controller,bytes(4))
            machine.mem_write(0xe5ff90,bytes(4))
            machine.mem_write(0xe5ff80,struct.pack('<I',display))
            machine.mem_write(0xb616c0,struct.pack('<I',game))
            machine.emu_start(n.CONTROL,n.CONTROL_END,count=100)
            self.assertEqual(machine.reg_read(UC_X86_REG_ECX),0)

    def test_native_control_transfer_removes_old_label_and_has_no_cpu_duplicates(self):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
        from unicorn.x86_const import UC_X86_REG_ESI,UC_X86_REG_ECX
        m=Uc(UC_ARCH_X86,UC_MODE_32);m.mem_map(0,0x1000000)
        m.mem_write(n.CONTROL,n.control_bytes())
        m.mem_write(0xe5ff80,struct.pack('<I',4));m.mem_write(0xb616c0,struct.pack('<I',11))
        m.mem_write(0xe60270,struct.pack('<I',1))  # old special-label path must not add CPU names
        def collect(assignments):
            result=[]
            for i,port in enumerate(assignments):
                entity,control=0x200000+i*0x100,0x210000+i*0x100
                m.mem_write(entity+0xc,struct.pack('<I',control))
                m.mem_write(entity+0x44,struct.pack('<f',2.0))  # old selection timers can still be positive
                m.mem_write(control,struct.pack('<I',port))
                m.reg_write(UC_X86_REG_ESI,entity)
                m.emu_start(n.CONTROL,n.CONTROL_END,count=100)
                if m.reg_read(UC_X86_REG_ECX):result.append(i)
            return result
        self.assertEqual(collect([0,1,2,3]+[0xffffffff]*18),[0,1,2,3])
        self.assertEqual(collect([0xffffffff,1,2,3,0]+[0xffffffff]*17),[1,2,3,4])
        self.assertEqual(collect([0xffffffff]*22),[])

    def test_native_selector_uses_last_name_for_both_settings_and_preserves_none(self):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESI,UC_X86_REG_EBX
        m=Uc(UC_ARCH_X86,UC_MODE_32);m.mem_map(0,0x1000000)
        m.mem_write(n.SELECTOR,n.selector_bytes())
        m.mem_write(0xf9d4c,bytes.fromhex('8b5e14'))
        record,name=0x200000,0x210000
        m.mem_write(record+0x14,struct.pack('<I',name));m.reg_write(UC_X86_REG_ESI,record)
        destinations=[]
        def stop(uc,address,size,user):
            if address in (0xf9d4f,0xf9dc7):destinations.append(address);uc.emu_stop()
        m.hook_add(UC_HOOK_CODE,stop)
        for option in (0,1,2,3,0xffffffff):
            m.mem_write(0xe5ff90,struct.pack('<I',option));m.reg_write(UC_X86_REG_EBX,0)
            m.emu_start(n.SELECTOR,0xf9dd0,count=30)
            self.assertEqual(destinations[-1],0xf9d4f if option<2 else 0xf9dc7)
            self.assertEqual(m.reg_read(UC_X86_REG_EBX),name if option<2 else 0)

    def test_career_guard_normalizes_only_exact_declared_nm1_bytes(self):
        raw=bytearray(b'\xcc'*0x6ed)
        at=n.CONTROL-0x75d90
        raw[at:at+len(n.CONTROL_BEFORE)]=n.CONTROL_BEFORE
        patched=bytearray(raw);patched[at:at+len(n.CONTROL_BEFORE)]=n.control_bytes()
        self.assertEqual(n.canonical_context(0x75d90,patched),raw)
        patched[at+7]^=1
        self.assertEqual(n.canonical_context(0x75d90,patched),patched)

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


try:
    from tests.nfl2k5_my_career_fixture import XBE as RETAIL_XBE  # the pinned retail extraction, if present
except Exception:  # the fixture is absent from an installed release tree
    RETAIL_XBE=Path("absent")


class LabelStyleTests(unittest.TestCase):
    """nl1 (Noah 2026-10-17): the old retail indicator is the default; nm1's label is kept as a choice."""

    def test_styles_default_to_retail_and_select_their_native_sites(self):
        self.assertEqual(n.DEFAULT_STYLE,"retail")
        self.assertEqual(n.STYLES,("retail","retail_persistent","scorebug"))
        sites=lambda style:[va for va,*_ in n.style_edits(style)]
        self.assertEqual(sites("retail"),[])
        self.assertEqual(sites("retail_persistent"),[n.CONTROL,n.SELECTOR])
        self.assertEqual(sites("scorebug"),[n.HOOK,n.CONTROL,n.SELECTOR])
        # The guards and cave reservations keep the union of every style.
        self.assertEqual([va for va,*_ in n.code_edits()],[n.HOOK,n.CONTROL,n.SELECTOR])
        with self.assertRaisesRegex(ValueError,"unknown label style"):
            n.style_edits("big")

    @unittest.skipUnless(RETAIL_XBE.is_file(),"retail default.xbe required")
    def test_each_style_on_the_retail_executable(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from mod_editor.core.nfl2k5_bump_strength import _sections,section_digest
        retail=RETAIL_XBE.read_bytes()
        same,receipt=n.apply_xbe(retail,"retail")
        self.assertEqual(same,retail)
        self.assertEqual((receipt["changed_bytes"],receipt["private_font"],receipt["persistent_human_names"]),(0,False,False))
        for style in ("retail_persistent","scorebug"):
            with self.subTest(style=style):
                out,receipt=n.apply_xbe(retail,style)
                image=XbeImage(out)
                self.assertEqual(image.read(n.CONTROL,len(n.control_bytes())),n.control_bytes())
                self.assertEqual(image.read(n.SELECTOR,len(n.selector_bytes())),n.selector_bytes())
                # The font binding (the private scorebug FONT) only in the scorebug style.
                self.assertEqual(image.read(n.HOOK,len(n.HOOK_BEFORE)),
                                 n.hook_bytes() if style=="scorebug" else n.HOOK_BEFORE)
                self.assertEqual(receipt["private_font"],style=="scorebug")
                self.assertTrue(receipt["persistent_human_names"])
                for section in _sections(out):
                    self.assertEqual(out[section.header_offset+36:section.header_offset+56],section_digest(out,section))
                # Bytes change only inside the declared sites and the .text digest.
                text=next(s for s in _sections(retail) if s.virtual_address<=n.HOOK<s.virtual_address+s.raw_size)
                allowed=set(range(text.header_offset+36,text.header_offset+56))
                for va,_,after,_ in n.style_edits(style):
                    at=XbeImage(retail).offset(va,len(after));allowed|=set(range(at,at+len(after)))
                self.assertEqual({i for i,(a,b) in enumerate(zip(retail,out)) if a!=b}-allowed,set())
                self.assertEqual(n.apply_xbe(out,style)[0],out)  # replay writes nothing new
        # Styles never mix: rebuild from the base to change the style.
        scorebug,_=n.apply_xbe(retail,"scorebug")
        with self.assertRaisesRegex(ValueError,"another label style"):
            n.apply_xbe(scorebug,"retail_persistent")
        with self.assertRaisesRegex(ValueError,"another label style"):
            n.apply_xbe(scorebug,"retail")

    def test_presets_keep_the_retail_label_and_the_atlas_choice(self):
        from mod_editor.core import mod_build
        # b776-sm1 (Noah, 2026-10-18): every preset, the SOFTDRINK ones included, installs the retail label. The
        # retail_persistent style (b775) labels only human-controlled players, so R1's show-names could not draw the
        # others; it and the scorebug style stay selectable.
        for name,values in mod_build.PRESETS.items():
            self.assertEqual(values["indicator_names_style"],"retail",name)
        self.assertEqual(mod_build.BuildPlan(source="a.iso",target="b.iso").indicator_names_style,"retail")
        plan=mod_build.apply_preset(mod_build.BuildPlan(source="retail.iso",target="out.iso"),"softdrink_experimental")
        self.assertEqual(plan.indicator_names_style,"retail")
        self.assertEqual(mod_build.apply_preset(mod_build.BuildPlan(source="retail.iso",target="out.iso"),"softdrink_advanced").indicator_names_style,"retail")
        self.assertIn("scorebug",__import__("mod_editor.core.nfl2k5_indicator_names",fromlist=["STYLES"]).STYLES)
        # The nm1 atlas stays in the bundle and the preset, one key away from the scorebug label.
        self.assertTrue(Path(plan.indicator_names_folder).as_posix().endswith("data/nfl2k5_indicator_names"))
        import dataclasses
        bare=mod_build.BuildPlan(source="a.iso",target="b.iso",indicator_names_folder=plan.indicator_names_folder)
        self.assertFalse(bare.wants_xbe_patch())  # an atlas folder alone no longer installs anything
        for style in ("retail_persistent","scorebug"):
            self.assertTrue(dataclasses.replace(bare,indicator_names_style=style).wants_xbe_patch())
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("indicator_names_style",settings.FEATURE_KEYS)

    def test_build_refuses_unknown_style_and_a_scorebug_label_without_its_atlas(self):
        from mod_editor.core import mod_build
        import dataclasses
        with tempfile.TemporaryDirectory() as folder:
            base=mod_build.BuildPlan(source=str(Path(folder)/"missing.iso"),target=str(Path(folder)/"out.iso"))
            with self.assertRaisesRegex(ValueError,"Player name label must be"):
                mod_build._build(dataclasses.replace(base,indicator_names_style="big"),_preflight_only=True)

    def test_build_step_installs_only_a_non_retail_style(self):
        import inspect
        from mod_editor.core import mod_build
        source=inspect.getsource(mod_build._build)
        self.assertIn('if plan.indicator_names_style != "retail":\n        # Final HUD writer',source)
        self.assertIn("style=plan.indicator_names_style",source)
        self.assertNotIn("if plan.indicator_names_folder:\n        # Final HUD writer",source)


if __name__=='__main__':
    unittest.main()
