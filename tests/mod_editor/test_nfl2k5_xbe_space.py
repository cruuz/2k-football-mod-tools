"""Standalone public geometry/writer tests and optional pinned-retail proofs."""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_depth_chart_storage as special
from mod_editor.core import nfl2k5_dynamic_kickoff as kickoff
from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, ReservationManifest, DEFAULT_MANIFEST
from mod_editor.core.nfl2k5_cave_manifest import Recorder

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None
HAVE_CS = importlib.util.find_spec("capstone") is not None
REQUESTS = (("alpha", "code", 25, 16), ("beta", "code", 7, 32), ("alpha", "data", 10, 4))


def repin(buf):
    for s in _sections(buf):
        buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    return bytes(buf)


def synthetic():
    """22 tiny invented sections in retail-sized sparse geometry, no game bytes."""
    buf = bytearray(special.RETAIL_FILE_SIZE)
    buf[:4] = b"XBEH"
    struct.pack_into("<3I", buf, 0x104, 0x10000, space.META_COPY, special.RETAIL_IMAGE_SIZE)
    struct.pack_into("<II", buf, 0x11C, 22, 0x10000 + space.TABLE)
    struct.pack_into("<II", buf, 0x170, space.logo.RETAIL_LOGO_VA, space.logo.LOGO_SIZE)
    buf[0xA10:0xA10 + space.logo.LOGO_SIZE] = space.logo.RETAIL_LOGO
    for i in range(22):
        name = 0x868 + i * 4
        buf[name:name + 4] = f"s{i:02d}".encode() + b"\0"
        flags, va, raw, size = 3, 0x11000 + i * 0x1000, 0x1000 + i * 0x1000, 4
        if i == 21:
            flags, va, raw, size = special.RETAIL_FLAGS, special.SECTION_VA, special.RETAIL_RAW, special.RETAIL_SIZE
        struct.pack_into("<9I", buf, space.TABLE + i * 56, flags, va, size, raw, size,
                         0x10000 + name, 0, 0x10840, 0x10840)
    return repin(buf)


def image_with_xbe(payload):
    from nfl2k5_xiso_fixture import dir_node, xiso
    neighbour = 64 + (len(payload) + 2047) // 2048
    root = dir_node([(64, len(payload), 0x80, "default.xbe"), (neighbour, 8, 0x80, "neighbour")])
    image = bytearray((neighbour + 1) * 2048)
    image[0x10000:0x10014] = image[0x107EC:0x10800] = xiso.XDVDFS_MAGIC
    struct.pack_into("<II", image, 0x10014, 33, len(root))
    image[33 * 2048:33 * 2048 + len(root)] = root
    image[64 * 2048:64 * 2048 + len(payload)] = payload
    image[neighbour * 2048:neighbour * 2048 + 8] = b"KEEPTHIS"
    return bytes(image)


class PublicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = synthetic()
        cls.pins = ExitStack()
        cls.addClassCleanup(cls.pins.close)
        for module, name, value in (
            (space, "METADATA_SHA256", space._sha(cls.retail[space.META_START:space.META_END])),
            (space, "GEOMETRY_SHA256", space._sha(b"".join(cls.retail[space.TABLE + i*56:space.TABLE + i*56 + 36] for i in range(22)))),
            (special, "RETAIL_CONTENT_SHA256", space._sha(bytes(special.RETAIL_SIZE))),
        ):
            cls.pins.enter_context(patch.object(module, name, value))
        cls.grown, cls.receipt = space.apply(cls.retail, REQUESTS)

    def test_layout_determinism_alignment_capacity_and_header_slack(self):
        self.assertEqual(space.status(self.retail), "retail")
        self.assertEqual(space.status(self.grown), "applied")
        self.assertEqual(space.apply(self.retail, reversed(REQUESTS))[0], self.grown)
        self.assertEqual(space.apply(self.grown, REQUESTS)[0], self.grown)
        self.assertEqual(space.apply(self.grown)[1]["changed_bytes"], 0)
        layout = space.layout(self.grown)
        self.assertEqual([a["va"] for a in layout["allocations"][:3]], [space.CODE_VA, space.DATA_VA, space.CODE_VA + 32])
        self.assertEqual(self.grown[space.META_COPY:space.NAMES], self.retail[space.META_START:space.META_END])
        self.assertEqual(len(self.grown), space.FILE_SIZE)
        image = XbeImage(self.grown)
        self.assertEqual(len(image.sections), 24)
        self.assertEqual(image.section(space.CODE_VA).flags, 0x36)
        self.assertEqual(image.section(space.DATA_VA).flags, 3)
        self.assertFalse(image.runtime_writable(space.CODE_VA, 4096))
        self.assertTrue(image.runtime_writable(space.DATA_VA, 4096))
        self.assertFalse(image.section(space.DATA_VA).executable)
        for before, after in zip(XbeImage(self.retail).sections, image.sections):
            self.assertEqual(self.retail[before.raw:before.raw + before.raw_size], self.grown[after.raw:after.raw + after.raw_size])
        for region in layout["regions"]:
            s = image.section(region["va"])
            head, tail = struct.unpack_from("<II", self.grown, s.header + 28)
            self.assertEqual(head, tail)  # both boundaries occupy the same page
            self.assertEqual(image.read(head, 2), b"\0\0")

    def test_request_errors_and_rebuild_refusal(self):
        for req in (("a", "code", 0, 1), ("a", "code", True, 1), ("a", "data", 1, 3),
                    ("a", "data", 1, 8192), ("a", "bad", 1, 1), ("A", "code", 1, 1)):
            with self.subTest(req=req), self.assertRaises(ValueError):
                space.apply(self.retail, [req])
        for requests in ([REQUESTS[0], REQUESTS[0]], [("a", "code", 4096, 1), ("b", "code", 1, 1)],
                         [("owner_" + str(i) * 50, "code", 1, 1) for i in range(8)]):
            with self.assertRaises(ValueError):
                space.apply(self.retail, requests)
        with self.assertRaisesRegex(ValueError, "differ"):
            space.apply(self.grown, [("different", "data", 1, 1)])

    def test_every_owned_component_is_pinned_and_foreign_refuses_before_mutation(self):
        for original, offsets in ((self.retail, (0x104, 0x108, 0x10C, 0x11C, 0x120, space.TABLE + 4, space.META_START, space.META_COPY, special.RETAIL_RAW)),
                                  (self.grown, (0x104, 0x108, 0x10C, 0x11C, space.META_START, space.META_START+28,
                                                space.META_COPY, space.NAMES, space.REFS, space.DIRECTORY+12,
                                                space.PAGE-1, special.RETAIL_RAW, space.CODE_RAW, space.DATA_RAW))):
            for off in offsets:
                bad = bytearray(original); bad[off] ^= 1; before = bytes(bad)
                with self.subTest(offset=hex(off), grown=original is self.grown):
                    self.assertEqual(space.status(before), "foreign")
                    with self.assertRaises(ValueError): space.apply(before, REQUESTS)
                    self.assertEqual(bytes(bad), before)
        for cut in (0, 4, 0x120, 0x1000, len(self.grown)-1):
            self.assertEqual(space.status(self.grown[:cut]), "foreign")
        self.assertEqual(space.status(self.grown + b"\0"), "foreign")

    def test_owned_code_installation_and_manifest_builder(self):
        code = b"\xc3" + b"\xcc" * 24
        result, _ = space.install_code(self.grown, "alpha", code)
        self.assertEqual(space.install_code(result, "alpha", code)[0], result)
        with self.assertRaisesRegex(ValueError, "foreign"):
            space.install_code(result, "alpha", b"\x90" * 25)
        with self.assertRaises(ValueError): space.install_code(result, "missing", code)
        recorder = Recorder(self.retail)
        recorder.observe(space, "apply", self.retail, self.grown, self.receipt)
        spans = recorder.finish(self.grown)
        for reservation in space.reservations(self.grown):
            self.assertTrue(any(s["start"] == reservation["start"] and s["end"] == reservation["end"]
                                and s["owner"] == reservation["owner"] for s in spans), reservation)
        self.assertTrue(any(s["owner"] == "alpha" and s["start"] == hex(space.DATA_VA) for s in spans))
        with self.assertRaises(ValueError):
            Recorder(self.retail).observe(space, "apply", self.retail, self.grown + b"\0", {})

    def test_boot_logo_transfers_owned_header_storage_before_new_headers(self):
        before = space.logo.apply(self.retail)[0]
        grown = space.apply(before, REQUESTS)[0]
        self.assertEqual(grown, self.grown)
        self.assertEqual(space.logo.status(grown), "applied")
        self.assertEqual(space.logo.apply(grown)[0], grown)
        va = struct.unpack_from("<I", grown, 0x170)[0]
        bitmap = XbeImage(grown).read(va, space.logo.LOGO_SIZE)
        self.assertEqual(bitmap, space.logo.RETAIL_LOGO)
        self.assertEqual(space.logo.decode_pixels(bitmap), (1700, 0))

    def _writer(self, source, target, failure=None):
        from mod_editor.core import platform_compat as io
        from mod_editor.core import nfl2k5_throw_tuning as tt
        image = image_with_xbe(source)
        with tempfile.TemporaryDirectory() as temporary:
            path = (Path(temporary) / "copy.iso").resolve()
            path.write_bytes(image)
            fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                if failure:
                    real_write, failed = io.pwrite, False
                    def injected(descriptor, data, off):
                        nonlocal failed
                        if not failed and (len(data) == 8 if failure == "directory" else len(data) == len(target)):
                            failed = True
                            real_write(descriptor, data[:3], off)
                            return 3
                        return real_write(descriptor, data, off)
                    with patch.object(io, "pwrite", injected), self.assertRaisesRegex(ValueError, "short"):
                        special.write_image_xbe(fd, target)
                    self.assertEqual(path.read_bytes(), image)
                    return
                receipt = special.write_image_xbe(fd, target)
                self.assertEqual(io.pread(fd, len(target), receipt["offset"]), target)
                self.assertEqual(tt._xdvdfs_module().xbe_extent(fd, os.fstat(fd).st_size), (receipt["offset"], len(target)))
                self.assertEqual(io.pread(fd, 8, len(image)-2048), b"KEEPTHIS")
                replay = special.write_image_xbe(fd, target)
                self.assertEqual(replay["image_growth"], 0)
                self.assertFalse(replay["relocated"])
            finally:
                os.close(fd)
            # Windows requires closed descriptors before replace.
            os.replace(path, path.with_suffix(".done"))

    def test_synthetic_disc_round_trip_and_all_rollback_paths(self):
        self._writer(self.retail, self.grown)
        self._writer(self.retail, self.grown, "directory")
        self._writer(self.retail, self.grown, "payload")
        self._writer(self.grown, self.grown, "payload")


@unittest.skipUnless(RETAIL.is_file(), f"pinned USA retail extraction missing: {RETAIL}")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        cls.legacy, _ = kickoff.apply(cls.retail)
        cls.grown, _ = relocated.apply(cls.legacy)

    def test_both_special_orders_byte_identical_and_writer_round_trip(self):
        from mod_editor.core import nfl2k5_edge_rename as edge, nfl2k5_modern_positions as modern
        from mod_editor.core import nfl2k5_position_pools as pools, nfl2k5_depth_chart_rows as rows
        prepared = self.legacy
        for module in (edge, modern, pools): prepared = module.apply(prepared)[0]
        special_only = rows.apply(prepared)[0]
        first = rows.apply(relocated.apply(prepared)[0])[0]
        second = relocated.apply(special_only)[0]
        self.assertEqual(first, second)
        self.assertEqual(rows.status(first), "applied")
        self.assertEqual(space.status(first), "applied")
        self.assertEqual(relocated.status(first), "applied")
        self.assertEqual(first[special.RETAIL_RAW:special.FILE_SIZE], special_only[special.RETAIL_RAW:special.FILE_SIZE])
        helper = PublicTests()
        helper._writer(self.retail, self.grown)
        helper._writer(special_only, first)
        helper._writer(self.grown, first)

    def test_fresh_allocation_proof_and_retired_cave_pin(self):
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(self.retail))
        self.assertEqual(space.allocation_evidence(self.retail, manifest)["encoded_references"], [])
        old = kickoff._offset(self.grown, kickoff.CAVE_VA, kickoff.CAVE_SIZE)
        self.assertEqual(self.grown[old:old+kickoff.CAVE_SIZE], self.legacy[old:old+kickoff.CAVE_SIZE])
        retail_direct = relocated.apply(self.retail)[0]
        self.assertEqual(retail_direct[old:old+kickoff.CAVE_SIZE], self.retail[old:old+kickoff.CAVE_SIZE])
        self.assertEqual(kickoff.status(self.grown), "applied")
        self.assertEqual(relocated.apply(self.grown)[0], self.grown)
        self.assertEqual(kickoff.apply(self.grown)[0], self.grown)

    def test_mixed_hooks_and_owner_corruption_refused_even_with_repinned_digest(self):
        for va, original in kickoff.HOOKS.values():
            bad = bytearray(self.grown)
            off = kickoff._offset(bad, va, len(original)); bad[off:off+len(original)] = original
            bad = repin(bad)
            self.assertEqual(relocated.status(bad), "foreign")
            with self.assertRaises(ValueError): relocated.apply(bad)
        bad = bytearray(self.grown); bad[space.CODE_RAW] ^= 1
        self.assertEqual(space.status(repin(bad)), "foreign")
        custom = dict(touchback_yard=30, cpu_landing_probability=72, cpu_target_yards=(2,18), cpu_touchback_probability=83)
        changed = relocated.apply(kickoff.apply(self.retail, **custom)[0])[0]
        self.assertEqual(relocated.read_settings(changed), {"status":"applied", **custom})
        with self.assertRaises(ValueError): relocated.apply(changed, touchback_yard=35)

    @unittest.skipUnless(HAVE_CS, "capstone is required for instruction equivalence")
    def test_every_instruction_is_identical_after_address_normalization(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        from capstone.x86 import X86_OP_MEM, X86_OP_IMM
        md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True
        old, _ = kickoff._code(kickoff._settings())
        code_va = relocated._sites(self.grown)[0]["va"]
        new, _ = relocated.code_for(kickoff._settings(), code_va, space.DATA_VA)
        old_ins, new_ins = list(md.disasm(old, kickoff.CAVE_VA)), list(md.disasm(new, code_va))
        self.assertEqual(sum(i.size for i in old_ins), len(old))
        self.assertEqual(sum(i.size for i in new_ins), len(new))
        self.assertEqual(len(old_ins), len(new_ins))
        def norm(address):
            if code_va <= address < code_va + kickoff.CAVE_SIZE: return address-code_va+kickoff.CAVE_VA
            if space.DATA_VA <= address < space.DATA_VA+7: return address-space.DATA_VA+kickoff.FLAGS
            if space.DATA_VA+7 <= address < space.DATA_VA+10: return address-space.DATA_VA-7+kickoff.TB_YARD
            return address
        for old_i, new_i in zip(old_ins, new_ins):
            self.assertEqual((old_i.id, old_i.size, len(old_i.operands)), (new_i.id, new_i.size, len(new_i.operands)))
            self.assertEqual(old_i.address-kickoff.CAVE_VA, new_i.address-code_va)
            for a, b in zip(old_i.operands, new_i.operands):
                self.assertEqual((a.type,a.size,a.access), (b.type,b.size,b.access))
                if a.type == X86_OP_MEM:
                    self.assertEqual((a.mem.segment,a.mem.base,a.mem.index,a.mem.scale,a.mem.disp),
                                     (b.mem.segment,b.mem.base,b.mem.index,b.mem.scale,norm(b.mem.disp)))
                elif a.type == X86_OP_IMM: self.assertEqual(a.imm, norm(b.imm))
                else: self.assertEqual(a.reg, b.reg)
            # Every changed byte must belong to an encoded immediate/displacement.
            allowed = set(range(new_i.imm_offset,new_i.imm_offset+new_i.imm_size)) | set(range(new_i.disp_offset,new_i.disp_offset+new_i.disp_size))
            self.assertTrue(all(a == b or i in allowed for i,(a,b) in enumerate(zip(old_i.bytes,new_i.bytes))))

    @unittest.skipUnless(HAVE_UC, "unicorn is required for bounded header-mapped execution")
    def test_header_mapped_relocated_reset_writes_data_and_returns_with_registers(self):
        import unicorn as uc
        from unicorn import x86_const as x86
        image = XbeImage(self.grown)
        machine = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        pages = {}
        for s in image.sections:
            if not s.flags & 2: continue
            for page in range(s.start & -4096, (s.end+4095)&-4096,4096):
                perms = uc.UC_PROT_READ | (uc.UC_PROT_EXEC if s.executable else 0) | (uc.UC_PROT_WRITE if s.writable else 0)
                pages[page] = pages.get(page,0) | perms
        for page in pages: machine.mem_map(page,4096)
        machine.mem_map(image.base,4096)
        machine.mem_write(image.base,self.grown[:image.headers_size])
        for s in image.sections:
            if s.flags & 2: machine.mem_write(s.start,self.grown[s.raw:s.raw+s.raw_size])
        for page,perms in pages.items(): machine.mem_protect(page,4096,perms)
        stack,stop = 0x3000000,0x3010000
        machine.mem_map(stack,4096);machine.mem_map(stop,4096,uc.UC_PROT_READ|uc.UC_PROT_EXEC)
        machine.mem_write(stack,struct.pack('<I',stop))
        # End the displaced-instruction continuation with RET, an explicit
        # bounded host stub; its destination and stack semantics remain checked.
        reset, original = kickoff.HOOKS['reset']; continuation=reset+len(original)
        machine.mem_write(continuation,b'\xc3')
        machine.mem_write(space.DATA_VA,b'\xff')
        before = bytes(machine.mem_read(0xA69000,4096))
        writes=[]
        machine.hook_add(uc.UC_HOOK_MEM_WRITE,lambda _m,_a,addr,size,value,_d:writes.append((addr,size,value)))
        machine.reg_write(x86.UC_X86_REG_ESP,stack)
        machine.reg_write(x86.UC_X86_REG_EBX,0x12345678)
        machine.reg_write(x86.UC_X86_REG_EFLAGS,0x246)
        machine.emu_start(reset,stop,count=30)
        self.assertEqual(machine.reg_read(x86.UC_X86_REG_EIP),stop)
        self.assertEqual(machine.reg_read(x86.UC_X86_REG_ESP),stack+4)
        self.assertEqual(machine.reg_read(x86.UC_X86_REG_EBX),0x12345678)
        self.assertEqual(machine.reg_read(x86.UC_X86_REG_EFLAGS),0x246)
        self.assertEqual(machine.reg_read(x86.UC_X86_REG_EAX),image.word(0x50D9A0))
        self.assertEqual(writes,[(space.DATA_VA,1,0)])
        self.assertEqual(bytes(machine.mem_read(0xA69000,4096)),before)
        self.assertEqual(machine.mem_read(space.DATA_VA,10),bytes(10))

    @unittest.skipUnless(HAVE_UC and HAVE_CS, "unicorn and capstone are required for retail lineup execution")
    def test_relocated_lineup_hold_and_contact_release_in_both_directions(self):
        spec = importlib.util.spec_from_file_location("kickoff_fixture", ROOT / "tests/mod_editor/test_nfl2k5_dynamic_kickoff.py")
        fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
        from mod_editor.core import nfl2k5_kick_rules as rules
        from tools import nfl2k5_kickoff_alignment as alignment
        payload = relocated.apply(rules.apply(self.legacy)[0])[0]
        for direction in (-1,1):
            m = fixture.Machine(payload, direction=direction, state_va=space.DATA_VA)
            before = bytes(m.uc.mem_read(0xA69000,4096))
            m.put(kickoff.PLAY_STATE,12)
            m.fpu_stubs[0x187780]=0; m.stub_pops[0x136D40]=0
            tee = m.readf(m.CTX+0x18)
            for slot,(x,z) in enumerate(alignment.kickoff_xz_2026()):
                who = m.KICKER if slot == 0 else m.COVERAGE
                m.uc.mem_write(who+0x2E,bytes([slot]))
                m.run(0x1840B0,ecx=who,edx=m.CONTACT)
                self.assertAlmostEqual(m.readf(m.CONTACT+8),tee+direction*z,places=3)
                self.assertEqual(m.flags(),0)
            m.put(kickoff.PLAY_STATE,14); m.launch()
            self.assertTrue(m.flags() & kickoff.ACTIVE)
            for who in (m.COVERAGE,m.BLOCKER):
                old=m.get(m.COUNTER)
                m.run(kickoff.HOOKS['plan'][0],ecx=who)
                m.run(kickoff.HOOKS['motion'][0],esi=who)
                self.assertEqual(m.get(m.COUNTER),old)
            m.position(0,direction*3657.6);m.event('ground')
            self.assertEqual(m.flags() & 7,kickoff.LANDING)
            old=m.get(m.COUNTER)
            m.run(kickoff.HOOKS['plan'][0],ecx=m.COVERAGE)
            self.assertEqual(m.get(m.COUNTER),old+1)
            self.assertEqual(bytes(m.uc.mem_read(0xA69000,4096)),before)


if __name__ == "__main__":
    unittest.main()
