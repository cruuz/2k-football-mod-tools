"""Standalone writer/ownership tests and bounded retail CPU proofs for widescreen v3.

No disc/pack is read into memory. CPU cases map only the 12 MB executable and
small camera/stack fixtures; missing private evidence or Unicorn skips precisely.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_widescreen as w
from mod_editor.core import nfl2k5_bump_strength as strength
from tests.nfl2k5_widescreen_test import build_xbe

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
    "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
try:
    import unicorn as u
    from unicorn import x86_const as r
except ImportError:
    u = r = None


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = build_xbe()

    def test_both_aspects_replay_and_exact_receipts(self):
        for aspect in w.ASPECTS:
            patched, receipt = w.apply(self.retail, aspect)
            self.assertEqual(w.status(patched, aspect), "applied")
            self.assertEqual(w.apply(patched, aspect)[0], patched)
            self.assertEqual(receipt["version"], 3)
            self.assertTrue(receipt["experimental"])
            self.assertFalse(receipt["runtime_witnessed"])
            self.assertEqual(len(receipt["edits"]), 11)
            for edit in receipt["edits"]:
                off = int(edit["file_offset"], 0)
                before, after = bytes.fromhex(edit["before"]), bytes.fromhex(edit["after"])
                self.assertEqual(self.retail[off:off + len(before)], before)
                self.assertEqual(patched[off:off + len(after)], after)
                self.assertEqual(hashlib.sha256(after).hexdigest(), edit["after_sha256"])

    def test_every_partial_install_and_foreign_context_refuses_before_mutation(self):
        for aspect in w.ASPECTS:
            patched, _ = w.apply(self.retail, aspect)
            for label, off, before, after in w._sites(self.retail, aspect):
                for base, value in ((self.retail, after), (patched, before)):
                    with self.subTest(aspect=aspect, site=label, applied=base is patched):
                        mixed = bytearray(base)
                        mixed[off:off + len(value)] = value
                        frozen = bytes(mixed)
                        self.assertEqual(w.status(frozen), "foreign")
                        with self.assertRaises(w.WidescreenPatchError):
                            w.apply(frozen, aspect)
                        self.assertEqual(bytes(mixed), frozen)
            for va, _pin in w.CONTEXT_PINS:
                bad = bytearray(patched)
                bad[w._offset(patched, va)] ^= 1
                self.assertEqual(w.status(bytes(bad)), "foreign")
                with self.assertRaises(w.WidescreenPatchError):
                    w.apply(bytes(bad), aspect)
            other = next(a for a in w.ASPECTS if a != aspect)
            with self.assertRaises(w.WidescreenPatchError):
                w.apply(patched, other)


@unittest.skipUnless(XBE.is_file(), "private USA retail default.xbe is absent")
class ManifestTests(unittest.TestCase):
    def test_build_plan_existing_flag_delivers_exact_v3_bytes(self):
        from mod_editor.core import mod_build
        retail = XBE.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp).resolve()
            source, target = directory / "default.xbe", directory / "wide.xbe"
            source.write_bytes(retail)
            plan = mod_build.BuildPlan(str(source), str(target), widescreen=True,
                name="Widescreen polish v3", notes="EXPERIMENTAL / UNWITNESSED")
            receipt = mod_build.build(plan)
            self.assertEqual(target.read_bytes(), w.apply(retail)[0])
            self.assertEqual(source.read_bytes(), retail)
            self.assertEqual(receipt["steps"][0]["widescreen"], "applied")
            self.assertEqual(mod_build.inspect(target)["widescreen"], "applied")
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["widescreen"])
        self.assertFalse(mod_build.PRESETS["softdrink_advanced"]["widescreen"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["widescreen"])

    def test_manifest_reserves_every_whole_site_including_unchanged_bytes(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        retail = XBE.read_bytes()
        patched, receipt = w.apply(retail)
        rec = Recorder(retail)
        rec.observe(w, "apply", retail, patched, receipt)
        image = XbeImage(retail)
        for label, off, before, _after in w._sites(retail, w.DEFAULT_ASPECT):
            va = image.va_for_offset(off)
            self.assertTrue(any(s["owner"] == "nfl2k5_widescreen"
                                and int(s["start"], 0) <= va
                                and int(s["end"], 0) >= va + len(before)
                                for s in rec.spans), label)
        for s in strength._sections(patched):
            self.assertEqual(patched[s.header_offset + 36:s.header_offset + 56],
                             strength.section_digest(patched, s))


@unittest.skipUnless(XBE.is_file() and u is not None, "private USA retail XBE or Unicorn is absent")
class RetailExecutionTests(unittest.TestCase):
    STACK = 0x7FF00000
    AREA = 0xF00000
    STOP = 0x0BADF00D
    SRC = AREA
    DST = AREA + 0x1000
    POINT = AREA + 0x2000
    OUT = AREA + 0x2100
    AUX = AREA + 0x2200

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched = {a: w.apply(cls.retail, a)[0] for a in w.ASPECTS}

    def load(self, payload):
        uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        uc.mem_map(0x10000, 0xEC0000 - 0x10000)
        uc.mem_write(0x10000, payload[:struct.unpack_from("<I", payload, 0x108)[0]])
        for s in strength._sections(payload):
            if s.virtual_address + s.raw_size <= 0xEC0000:
                uc.mem_write(s.virtual_address, payload[s.raw_offset:s.raw_offset + s.raw_size])
        uc.mem_protect(0x11000, 0x4E9000 - 0x11000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        uc.mem_map(self.STACK - 0x10000, 0x20000)
        uc.mem_map(self.AREA, 0x10000)
        uc.mem_map(self.STOP & ~0xFFF, 0x1000)
        uc.mem_write(0xA6A9D0, struct.pack("<II", 720, 480))
        uc.mem_write(0xA6AFB4, struct.pack("<I", w.ACTIVE_CAMERA_VA))
        uc.reg_write(r.UC_X86_REG_FPCW, 0x37F)
        return uc

    def execute(self, uc, entry, *, ecx=None, edx=None, args=(), stop=None, stack=None, at_call=False):
        sp = self.STACK if stack is None else stack
        words = args if at_call else (self.STOP, *args)
        uc.mem_write(sp, struct.pack("<" + "I" * len(words), *words))
        uc.reg_write(r.UC_X86_REG_ESP, sp)
        if ecx is not None:
            uc.reg_write(r.UC_X86_REG_ECX, ecx)
        if edx is not None:
            uc.reg_write(r.UC_X86_REG_EDX, edx)
        end = self.STOP if stop is None else stop
        hit = []
        def check(machine, address, _size, _data):
            if address == end:
                hit.append(address)
                machine.emu_stop()
        handle = uc.hook_add(u.UC_HOOK_CODE, check)
        try:
            uc.emu_start(entry, self.STOP if stop is None else 0, count=10000)
            self.assertEqual(uc.reg_read(r.UC_X86_REG_EIP), end, "instruction bound/return")
        finally:
            uc.hook_del(handle)
        return bytes(uc.mem_read(w.ACTIVE_CAMERA_VA, w.CAMERA_SIZE))

    def camera(self, *, perspective=True, target=(40, 16, 680, 464), stamp=0, plane=False):
        b = bytearray(w.CAMERA_SIZE)
        struct.pack_into("<16f", b, 0x40, 1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1)
        struct.pack_into("<I", b, 0x220, int(perspective))
        struct.pack_into("<8f", b, 0x230, -320,224,-1,0, 320,-224,-1000,0)
        struct.pack_into("<I", b, w.STAMP_OFFSET, stamp)
        x0,y0,x1,y1 = target
        struct.pack_into("<8f", b, 0x250, x0,y0,0,0,x1,y1,1,0)
        struct.pack_into("<f", b, 0x270, 35 / 18)
        if plane:
            struct.pack_into("<4f", b, 0x1C0, 4,5,-30,1)
            struct.pack_into("<4f", b, 0x1D0, .6,.8,0,0)
            struct.pack_into("<fI", b, 0x1E0, 100, 1)
        return bytes(b)

    @staticmethod
    def f(uc, va, count=1):
        return struct.unpack("<" + "f" * count, uc.mem_read(va, count * 4))

    def activate(self, uc, camera=None, source=None):
        source = self.SRC if source is None else source
        if camera is not None:
            uc.mem_write(source, camera)
        before = bytes(uc.mem_read(source, w.CAMERA_SIZE))
        result = self.execute(uc, 0x2AC80, ecx=source, stop=w.RENDER_LIST_VA)
        self.assertEqual(bytes(uc.mem_read(source, w.CAMERA_SIZE)), before)
        return result

    def consume_reciprocal(self, uc):
        # Retail callers consume the projector's ST(0) return before more math.
        # Leaving it on the x87 stack would make this harness overflow falsely.
        stub = self.AREA + 0x3000
        uc.mem_write(stub, b"\xdd\xd8\xc3")
        self.execute(uc, stub)

    def test_both_interlaced_fields_and_projected_plane_match(self):
        for aspect in w.ASPECTS:
            for perspective, target in ((True, (40,16,680,464)), (False, (40,16,680,464)),
                                        (True, (60,120,260,400)), (True, (0,0,720,480))):
                for interlaced, matched in ((0,True), (1,True), (1,False)):
                    with self.subTest(aspect=aspect, perspective=perspective, target=target,
                                      interlaced=interlaced, matched=matched):
                        uc = self.load(self.patched[aspect])
                        uc.mem_write(0xA6A9CC, struct.pack("<I", interlaced))
                        uc.mem_write(0xA6AA18, struct.pack("<I", 0))
                        uc.mem_write(0xA6AA20, struct.pack("<I", 0x1234))
                        uc.mem_write(0xA6AA58, struct.pack("<I", 0x1234 if matched else 0x5678))
                        camera = self.camera(perspective=perspective, target=target, plane=True)
                        uc.mem_write(self.SRC, camera)
                        self.execute(uc, w.REBUILD_VA, ecx=self.SRC)
                        retail = bytes(uc.mem_read(self.SRC, w.CAMERA_SIZE))
                        got = self.activate(uc)
                        inv = w.constants(aspect)["inv_stretch"]
                        self.assertAlmostEqual(struct.unpack_from("<f", got)[0],
                                               struct.unpack_from("<f", retail)[0] * inv, places=3)
                        for base in (0, 0xF0):
                            for i in range(16):
                                if i % 4:
                                    self.assertEqual(got[base+4*i:base+4*i+4], retail[base+4*i:base+4*i+4])
                        if interlaced and matched:
                            for first, second in ((0,0x130), (0xF0,0x170)):
                                for i in range(16):
                                    expected = got[first+4*i:first+4*i+4] if i % 4 == 0 else retail[second+4*i:second+4*i+4]
                                    self.assertEqual(got[second+4*i:second+4*i+4], expected)
                        else:
                            self.assertEqual(got[0x130:0x1B0], retail[0x130:0x1B0])
                        # Independently rerun the real plane builder on the corrected projection.
                        uc.mem_write(self.DST, got)
                        self.execute(uc, w.PLANE_VA, args=(self.DST,))
                        self.assertEqual(got[0x1B0:0x1C0], bytes(uc.mem_read(self.DST+0x1B0,16)))
                        self.assertNotEqual(got[0x1B0:0x1BC], retail[0x1B0:0x1BC])
                        self.assertEqual(self.activate(uc, got, self.DST), got)

    def test_actual_sphere_cull_accepts_new_edges_but_keeps_depth_and_vertical_bounds(self):
        uc = self.load(self.patched["16:9"])
        uc.mem_write(self.SRC, self.camera())
        self.execute(uc, w.REBUILD_VA, ecx=self.SRC)
        self.activate(uc)
        for point, expected_retail, expected_wide in (
                ((56,0,-100,1),0,1), ((-56,0,-100,1),0,1),
                ((80,0,-100,1),0,0), ((0,80,-100,1),0,0),
                ((0,0,100,1),0,0), ((0,0,-1500,1),0,0), ((0,0,-100,1),1,1)):
            uc.mem_write(self.POINT, struct.pack("<4f", *point))
            for cam, expected in ((self.SRC,expected_retail),(w.ACTIVE_CAMERA_VA,expected_wide)):
                self.execute(uc, 0x2ADC0, ecx=cam, edx=self.POINT, args=(0,))
                self.assertEqual(uc.reg_read(r.UC_X86_REG_EAX), expected, (point,hex(cam)))

    def test_sky_fills_world_width_and_uses_wide_horizontal_but_retail_vertical_angle(self):
        for aspect in w.ASPECTS:
            for target in ((40,16,680,464),(40,96,680,384),(0,0,720,480),(60,120,260,400)):
                with self.subTest(aspect=aspect,target=target):
                    uc = self.load(self.patched[aspect])
                    saved = self.activate(uc,self.camera(target=target))
                    uc.mem_write(self.DST,saved)
                    self.execute(uc,0x9E110,ecx=self.DST)
                    vertical_angle = uc.reg_read(r.UC_X86_REG_EAX)
                    sky = self.activate(uc,self.camera(perspective=False,target=target),w.SKY_CAMERA_VA)
                    uc.reg_write(r.UC_X86_REG_EBX,self.DST)
                    self.execute(uc,w.SKY_LENS_HOOK_VA,stop=0x9E1CA)
                    lens = self.f(uc,self.STACK+0x14)[0]
                    full = target[0] in (0,40) and target[2] in (680,720)
                    expected = (35/18)/w.stretch(aspect) if full else 35/18
                    self.assertAlmostEqual(lens,expected,places=6)
                    if full:
                        clip = struct.unpack_from("<I",sky,0x200)[0]
                        self.assertEqual((clip&0xFFFF,(clip>>16)+1),(target[0],target[2]))
                        self.assertEqual(struct.unpack_from("<I",sky,w.STAMP_OFFSET)[0],w.STAMP_NONE)
                        self.assertAlmostEqual(struct.unpack_from("<f",sky)[0],(target[2]-target[0])/640,places=6)
                    self.execute(uc,0x9E110,ecx=self.DST)
                    self.assertEqual(uc.reg_read(r.UC_X86_REG_EAX),vertical_angle)
                    self.assertEqual(bytes(uc.mem_read(self.DST,w.CAMERA_SIZE)),saved)

    def test_world_to_marker_to_pixel_hud_lands_at_same_widened_pixel(self):
        for aspect in w.ASPECTS:
            uc = self.load(self.patched[aspect])
            world = self.activate(uc,self.camera())
            uc.mem_write(self.DST,world)
            self.execute(uc,0x66950,ecx=self.SRC,edx=self.DST)
            self.activate(uc,source=self.SRC)
            # Visible in the added strip for both 16:9 and the narrower 16:10.
            uc.mem_write(self.AUX,struct.pack("<4f",54,8,-100,1))
            self.execute(uc,w.PROJECT_VA,ecx=self.DST,edx=self.AUX,args=(self.POINT,))
            true_pixel = self.f(uc,self.POINT,4)
            self.consume_reciprocal(uc)
            self.execute(uc,0xFA2A1,ecx=self.DST,edx=self.AUX,args=(self.POINT,),at_call=True,stop=0xFA2A6)
            pixel_hud_position = self.f(uc,self.POINT,4)
            self.consume_reciprocal(uc)
            self.assertGreater(pixel_hud_position[0],true_pixel[0])
            # Native pixel HUD sees absolute frame coordinates; its view subtracts frame centre.
            uc.mem_write(self.POINT+8,struct.pack("<f",0))
            self.execute(uc,w.PROJECT_VA,ecx=w.ACTIVE_CAMERA_VA,edx=self.POINT,args=(self.OUT,))
            final_pixel = self.f(uc,self.OUT,4)
            self.consume_reciprocal(uc)
            self.assertAlmostEqual(final_pixel[0],true_pixel[0],places=3)
            self.assertAlmostEqual(final_pixel[1],true_pixel[1],places=3)
            self.execute(uc,0x2ADC0,ecx=w.ACTIVE_CAMERA_VA,edx=self.POINT,args=(0x3F800000,))
            self.assertEqual(uc.reg_read(r.UC_X86_REG_EAX),1,
                             "world-edge labels must survive the HUD cull before text clamping")
            bounds = bytes(uc.mem_read(w.ACTIVE_CAMERA_VA+0x284,8))
            uc.mem_write(w.ACTIVE_CAMERA_VA+0x284,struct.pack("<2f",-320,320))
            self.execute(uc,0x2ADC0,ecx=w.ACTIVE_CAMERA_VA,edx=self.POINT,args=(0x3F800000,))
            self.assertEqual(uc.reg_read(r.UC_X86_REG_EAX),0,"old bounds clamp this visible label")
            uc.mem_write(w.ACTIVE_CAMERA_VA+0x284,bounds)
            uc.mem_write(self.POINT,struct.pack("<f",800))
            self.execute(uc,0x2ADC0,ecx=w.ACTIVE_CAMERA_VA,edx=self.POINT,args=(0x3F800000,))
            self.assertEqual(uc.reg_read(r.UC_X86_REG_EAX),0,"offscreen labels still cull")

    def test_projector_leaves_untransformed_sources_alone(self):
        uc = self.load(self.patched["16:9"])
        uc.mem_write(self.SRC,self.camera())
        self.execute(uc,w.REBUILD_VA,ecx=self.SRC)
        uc.mem_write(self.POINT,struct.pack("<4f",56,8,-100,1))
        self.execute(uc,w.PROJECT_VA,ecx=self.SRC,edx=self.POINT,args=(self.OUT,))
        native = bytes(uc.mem_read(self.OUT,16))
        self.consume_reciprocal(uc)
        for site in w.HUD_PROJECT_CALLS:
            self.execute(uc,site,ecx=self.SRC,edx=self.POINT,args=(self.OUT,),at_call=True,stop=site+5)
            self.assertEqual(bytes(uc.mem_read(self.OUT,16)),native)
            self.consume_reciprocal(uc)

    def test_shadow_call_uses_exact_active_camera_and_preserves_stack(self):
        for payload, expected in ((self.retail,0), (self.patched["16:9"],1)):
            uc = self.load(payload)
            uc.mem_write(self.SRC, self.camera())
            self.execute(uc, w.REBUILD_VA, ecx=self.SRC)
            self.activate(uc)
            uc.mem_write(self.STACK+0xB4, bytes(uc.mem_read(self.SRC,w.CAMERA_SIZE)))
            uc.mem_write(self.POINT, struct.pack("<4f",56,0,-100,1))
            # At the real LEA hook the radius is already at [esp].
            self.execute(uc, w.SHADOW_CAMERA_VA, edx=self.POINT, stop=0x1C3307,
                     args=(0,), at_call=True)
            self.assertEqual(uc.reg_read(r.UC_X86_REG_EAX), expected)
            self.assertEqual(uc.reg_read(r.UC_X86_REG_ESP), self.STACK+4)

    def test_all_five_projector_hooks_preserve_depth_y_and_native_return(self):
        for aspect in w.ASPECTS:
            uc = self.load(self.patched[aspect])
            for stamp, perspective in ((0,True), (w.STAMP_DIAGRAM,True), (0,False)):
                got = self.activate(uc, self.camera(perspective=perspective,stamp=stamp))
                uc.mem_write(self.DST, got)  # saved active copy, as in FUN_0007f840
                for point in ((-56,0,-100,1),(0,12,-100,1),(56,-8,-100,1)):
                    uc.mem_write(self.POINT, struct.pack("<4f", *point))
                    self.execute(uc,w.PROJECT_VA,ecx=self.DST,edx=self.POINT,args=(self.OUT,))
                    native = self.f(uc,self.OUT,4)
                    # Drain/record the native reciprocal depth with a bounded FSTP stub.
                    stub = self.AREA+0x3000
                    uc.mem_write(stub,b"\xd9\x1d"+struct.pack("<I",self.AUX)+b"\xc3")
                    self.execute(uc,stub)
                    depth = self.f(uc,self.AUX)[0]
                    for site in w.HUD_PROJECT_CALLS:
                        for reg in (r.UC_X86_REG_EBX,r.UC_X86_REG_ESI,r.UC_X86_REG_EDI,r.UC_X86_REG_EBP):
                            uc.reg_write(reg,0x12345678)
                        # Execute the actual patched CALL, with its output argument on the stack.
                        self.execute(uc,site,ecx=self.DST,edx=self.POINT,args=(self.OUT,),
                                 at_call=True,stop=site+5)
                        actual = self.f(uc,self.OUT,4)
                        self.assertAlmostEqual(actual[0],360+(native[0]-360)*w.stretch(aspect),places=3)
                        self.assertEqual(actual[1:],native[1:])
                        self.assertEqual(uc.reg_read(r.UC_X86_REG_ESP), self.STACK+4)
                        for reg in (r.UC_X86_REG_EBX,r.UC_X86_REG_ESI,r.UC_X86_REG_EDI,r.UC_X86_REG_EBP):
                            self.assertEqual(uc.reg_read(reg),0x12345678)
                        self.execute(uc,stub)
                        self.assertEqual(self.f(uc,self.AUX)[0],depth)

    def test_world_pixel_hud_keeps_edge_clip_and_diagram_keeps_its_window(self):
        for target, source, expected_stamp in (((40,16,680,464),self.SRC,w.STAMP_PIXELS),
                                              ((0,0,720,480),self.SRC,w.STAMP_PIXELS),
                                              ((60,120,260,400),w.DIAGRAM_CAMERA_VA,0x3F800000)):
            uc = self.load(self.patched["16:9"])
            camera = self.camera(target=target)
            uc.mem_write(source,camera)
            self.execute(uc,w.REBUILD_VA,ecx=source)
            if source == self.SRC:
                self.activate(uc,source=source)
                source = w.ACTIVE_CAMERA_VA
            self.execute(uc,0x66950,ecx=self.DST,edx=source)
            stamp = struct.unpack("<I",uc.mem_read(self.DST+w.STAMP_OFFSET,4))[0]
            self.assertEqual(stamp,expected_stamp)
            built = bytes(uc.mem_read(self.DST,w.CAMERA_SIZE))
            got = self.activate(uc,source=self.DST)
            clip = struct.unpack_from("<I",got,0x200)[0]
            if expected_stamp == w.STAMP_PIXELS:
                self.assertEqual(clip,struct.unpack_from("<I",built,0x200)[0])
                self.assertAlmostEqual(struct.unpack_from("<f",got)[0],27/32,places=6)
                # A marker at frame x=660 survives, even though menu clipping ends at 630.
                self.assertLessEqual(clip & 0xFFFF,660)
                self.assertGreaterEqual(clip >> 16,660)
            else:
                self.assertEqual((clip & 0xFFFF,(clip >> 16)+1),(107,276))
            self.assertEqual(self.activate(uc,got,self.SRC),got)

    def test_one_pixel_scissors_and_gpu_field_selection(self):
        uc = self.load(self.patched["16:9"])
        for rounding in (0,0x400,0x800,0xC00):
            uc.reg_write(r.UC_X86_REG_FPCW,0x37F|rounding)
            got = self.activate(uc,self.camera(perspective=False,target=(43,16,44,464)))
            clip = struct.unpack_from("<I",got,0x200)[0]
            self.assertGreaterEqual(clip >> 16,clip & 0xFFFF)
        uc.reg_write(r.UC_X86_REG_FPCW,0x37F)
        uc.mem_write(0xA6A9CC,struct.pack("<I",1))
        uc.mem_write(0xA6AA18,struct.pack("<I",0))
        uc.mem_write(0xA6AA20,struct.pack("<I",0x1234))
        uc.mem_write(0xA6AA58,struct.pack("<I",0x1234))
        got = self.activate(uc,self.camera(perspective=False))
        for field, matrix in ((0,0xF0),(1,0x170)):
            state, fifo = self.AREA+0x4000,self.AREA+0x5000
            uc.mem_write(state,bytes(0x400))
            uc.mem_write(state+0xC,struct.pack("<I",fifo))
            uc.mem_write(0xA6AA00,struct.pack("<I",field))
            self.execute(uc,0x2B5B0,ecx=state,edx=w.ACTIVE_CAMERA_VA,stop=0x2A5B0)
            self.assertEqual(uc.reg_read(r.UC_X86_REG_ECX),w.ACTIVE_CAMERA_VA+matrix)
            words = struct.unpack("<8I",uc.mem_read(fifo,32))
            self.assertEqual(words[4:6],(0x402C0,(629<<16)|90))
            self.assertEqual(self.f(uc,w.ACTIVE_CAMERA_VA+matrix)[0],27/32)


if __name__ == "__main__":
    unittest.main()
