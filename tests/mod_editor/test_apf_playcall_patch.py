"""Standalone synthetic instruction/transport tests; never launch a game."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_playcall_patch as p
from mod_editor.core.errors import ValidationError


MASK64 = (1 << 64) - 1


class SyntheticMachine:
    """Evaluate only the emitted leaf's integer instructions over synthetic RAM.

    This is a small test oracle for actual bytes (including saved upper halves,
    CR, stack, branch displacement and stores), not game emulation. Unsupported
    instructions and out-of-region reads/writes fail immediately.
    """
    def __init__(self, hook=p.PROFILES[0].hook):
        rng = random.Random(74)
        self.r = [rng.getrandbits(64) for _ in range(32)]
        self.cr = 0x9A7B6C5D
        self.lr, self.ctr = rng.getrandbits(64), rng.getrandbits(64)
        self.mem = {}
        self.hook = hook
        self.add(0x10000, bytes(0x1000))  # private stack region
        self.r[1] = 0x10800
        self.book, self.master = 0x20000, 0x40000
        self.add(self.book, bytes(0x7E20))
        self.add(self.master, bytes(0x18000))
        self.put(self.master + 0x34, 163, 4)
        self.put(self.master + 0x38, 586, 4)
        self.put(self.master + 0x3C, 28, 4)
        self.put(self.book + 0x7E0C, self.master, 4)
        # Categories 3 and 7 have TE roles, 6 has only WRs.
        for c in (3, 6, 7):
            for slot in range(11):
                self.put(self.master + 0x44 + 16*c + 5 + slot, 9, 1)
        self.put(self.master + 0x44 + 16*3 + 5, 8, 1)
        self.put(self.master + 0x44 + 16*7 + 5, 8 | 0x40, 1)  # depth bits
        self.put(self.book + 0x7E04, (1 << 3) | (1 << 6) | (1 << 7), 4)
        for rec in range(176):
            for entry in range(84):
                self.put(self.book + 0x70 + 176*rec + 2*entry, 0x13FF, 2)
        self.r[24], self.r[27], self.r[29], self.r[30] = 0, 2, self.book, 0

    def add(self, address, data):
        self.mem.update((address+i, v) for i, v in enumerate(data))

    def get(self, address, size):
        return int.from_bytes(bytes(self.mem[address+i] for i in range(size)), "big")

    def put(self, address, value, size):
        for i, v in enumerate((value & ((1 << (size*8))-1)).to_bytes(size, "big")):
            if address+i not in self.mem:
                raise AssertionError(f"Write outside synthetic region: {address+i:#x}")
            self.mem[address+i] = v

    def record(self, index, plays, cat=3, form=None):
        base = self.book + 0x70 + index*176
        for i, play in enumerate(plays):
            self.put(base+i*2, 0x1000 | play, 2)
        self.put(base+0xA8, ((index if form is None else form) << 24) | cat << 17, 4)
        self.put(base+0xAC, 1 << cat, 4)

    def candidates(self, ids):
        self.r[28] = len(ids)
        for i, play in enumerate(ids):
            address = self.master + 0x80C4 + 100*play
            self.put(address+4, 0, 4); self.put(address+8, 2, 4)
            self.put(self.r[1]+0x50+4*i, address, 4)
        self.ids = ids

    @staticmethod
    def signed(x, bits):
        x &= (1 << bits)-1
        return x-(1 << bits) if x & (1 << (bits-1)) else x

    def run(self):
        cave = p.assemble_cave(self.hook)
        words = dict((p.CAVE_START+i, int.from_bytes(cave[i:i+4], "big")) for i in range(0,len(cave),4))
        self.before = self.r.copy(); original_cr = self.cr
        outside = {a:v for a,v in self.mem.items() if not 0x10000 <= a < 0x11000}
        pc = p.CAVE_START
        for step in range(2_000_000):
            if pc == self.hook+4:
                break
            w = words[pc]; op=w>>26; rt=w>>21&31; ra=w>>16&31; rb=w>>11&31
            imm=self.signed(w,16); nextpc=pc+4
            if op in (14,15):
                self.r[rt] = ((self.r[ra] if ra else 0) + (imm << (16 if op==15 else 0))) & MASK64
            elif op in (32,34,40):
                self.r[rt] = self.get((self.r[ra]+imm)&MASK64,{32:4,34:1,40:2}[op])
            elif op == 36:
                self.put((self.r[ra]+imm)&MASK64,self.r[rt],4)
            elif op in (58,62):
                address=(self.r[ra]+self.signed(w & 0xFFFC,16)) & MASK64
                if op==58:self.r[rt]=self.get(address,8)
                else:
                    self.put(address,self.r[rt],8)
                    if w&1:self.r[ra]=address
            elif op==7:
                self.r[rt]=(self.r[ra]*imm)&MASK64
            elif op==10:
                left,right=self.r[ra]&0xFFFFFFFF,w&0xFFFF
                shift=28-4*(rt>>2)
                self.cr=(self.cr & ~(15<<shift)) | ((8 if left<right else 4 if left>right else 2)<<shift)
            elif op==21:
                sh,mb,me=rb,w>>6&31,w>>1&31
                mask=sum(1<<(31-i) for i in range(32) if (mb<=i<=me if mb<=me else i>=mb or i<=me))
                value=self.r[rt]&0xFFFFFFFF
                self.r[ra]=((value<<sh)|(value>>(32-sh))) & mask
            elif op==28:
                self.r[ra]=self.r[rt] & (w&0xFFFF)
                value=self.r[ra]
                self.cr=(self.cr&0x0FFFFFFF) | ((2 if value==0 else 8 if value>>63 else 4)<<28)
            elif op==18:
                nextpc=pc+self.signed(w&0x3FFFFFC,26)
            elif op==16:
                bo,bi=rt,ra
                bit=(self.cr>>(31-bi))&1
                if (bo==12 and bit) or (bo==4 and not bit):nextpc=pc+self.signed(w&0xFFFC,16)
                if bo not in (4,12):raise AssertionError('Unexpected BO')
            elif op==31:
                xo=w>>1&1023
                if xo==19:self.r[rt]=self.cr
                elif xo==144:self.cr=self.r[rt]&0xFFFFFFFF
                elif xo==32:
                    left,right=self.r[ra]&0xFFFFFFFF,self.r[rb]&0xFFFFFFFF
                    shift=28-4*(rt>>2)
                    self.cr=(self.cr&~(15<<shift)) | ((8 if left<right else 4 if left>right else 2)<<shift)
                elif xo==444:self.r[ra]=self.r[rt]|self.r[rb]
                elif xo==28:self.r[ra]=self.r[rt]&self.r[rb]
                elif xo==24:
                    shift=self.r[rb]&63;self.r[ra]=(self.r[rt]<<shift)&0xFFFFFFFF if shift<32 else 0
                elif xo==23:self.r[rt]=self.get(self.r[ra]+self.r[rb],4)
                elif xo==151:self.put(self.r[ra]+self.r[rb],self.r[rt],4)
                elif xo==40:self.r[rt]=(self.r[rb]-self.r[ra])&MASK64
                elif xo==266:self.r[rt]=(self.r[ra]+self.r[rb])&MASK64
                elif xo==459:self.r[rt]=(self.r[ra]&0xFFFFFFFF)//(self.r[rb]&0xFFFFFFFF)
                else:raise AssertionError(f'Unsupported XO {xo}')
            else:raise AssertionError(f'Unsupported opcode {op}')
            pc=nextpc
        else:raise AssertionError('Cave exceeded bounded instruction budget')
        assert self.cr==original_cr
        for r in range(32):
            if r not in (11,28):assert self.r[r]==self.before[r],r
        assert self.r[11] & 0xFFFFFFFF == 0x85060000
        assert all(self.mem[a]==v for a,v in outside.items())
        return [(self.get(self.r[1]+0x50+4*i,4)-self.master-0x80C4)//100 for i in range(self.r[28])]


class CaveTests(unittest.TestCase):
    def test_compacts_stably_and_preserves_registers_and_memory(self):
        for profile in p.PROFILES:
            m=SyntheticMachine(profile.hook);m.record(0,[1,3],3);m.record(1,[2,4],6)
            m.candidates([4,3,2,1]);self.assertEqual(m.run(),[3,1])

    def test_zero_matches_is_exact_fallback(self):
        m=SyntheticMachine();m.record(0,[1,2],6);m.candidates([2,1]);self.assertEqual(m.run(),[2,1])

    def test_every_pass_subtype_and_full_forty_candidate_buffer(self):
        for subtype in (2,3,4):
            m=SyntheticMachine();m.record(0,list(range(40)),7);m.candidates(list(range(40)));m.r[27]=subtype
            self.assertEqual(m.run(),list(range(40)))

    def test_wrong_family_subtype_and_mixed_buffer_are_untouched(self):
        for family,subtype in ((1,2),(0,0),(0,1),(0,5),(0,-1)):
            m=SyntheticMachine();m.record(0,[1],3);m.candidates([2,1]);m.r[24]=family;m.r[27]=subtype&MASK64
            self.assertEqual(m.run(),[2,1])
        m=SyntheticMachine();m.record(0,[1],3);m.candidates([1,2]);m.put(m.master+0x80C4+200+8,8,4)
        self.assertEqual(m.run(),[1,2])  # reject after an earlier match; no partial commit

    def test_mask_word_b_first_empty_and_formation_filter(self):
        for kind in ('mask','word_b','hole','form'):
            m=SyntheticMachine();m.record(0,[2],6);m.record(1,[1],3);m.candidates([2,1])
            if kind=='mask':m.put(m.book+0x7E04,1<<6,4)
            if kind=='word_b':m.put(m.book+0x70+176+0xAC,1<<6,4)
            if kind=='hole':m.put(m.book+0x70,0x13FF,2)
            if kind=='form':m.r[30]=m.master+0x244  # record zero, no TE
            self.assertEqual(m.run(),[2,1],kind)

    def test_84th_entry_and_last_record_bounds(self):
        m=SyntheticMachine()
        for i in range(175):m.record(i,[2],6,form=0)
        m.record(175,[2]*83+[1],3,form=2);m.candidates([3,1])
        self.assertEqual(m.run(),[1])

    def test_null_and_malformed_inputs_keep_original(self):
        for kind in ('null_book','null_master','catalog','bad_pointer','category'):
            m=SyntheticMachine();m.record(0,[1],3);m.candidates([2,1])
            if kind=='null_book':m.r[29]=0
            if kind=='null_master':m.put(m.book+0x7E0C,0,4)
            if kind=='catalog':m.put(m.master+0x38,10,4)
            if kind=='bad_pointer':m.put(m.r[1]+0x50,m.master+0x80C4+1,4)
            if kind=='category':m.put(m.book+0x70+0xA8,99<<17,4)
            before=[m.get(m.r[1]+0x50+i*4,4) for i in range(2)]
            m.run();self.assertEqual([m.get(m.r[1]+0x50+i*4,4) for i in range(2)],before)

    def test_decoder_rejects_modified_and_escaping_branches(self):
        cave=p.assemble_cave(p.PROFILES[0].hook)
        self.assertTrue(p.verify_cave(cave,p.PROFILES[0].hook)['all_branch_targets_checked'])
        for altered in (cave[:-1],struct.pack('>I',0x48001000)+cave[4:],bytes(4)+cave[4:]):
            with self.assertRaises(ValidationError):p.verify_cave(altered,p.PROFILES[0].hook)


class SyntheticImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Only our authored hook instruction and zeros; no game bytes.
        image=bytearray(p.IMAGE_SIZE);profile=p.PROFILES[0];o=profile.hook-p.IMAGE_BASE
        struct.pack_into('>I',image,o,0x3D608506)
        cls.image=bytes(image)
        cls.profile=replace(profile,sha256=hashlib.sha256(image).hexdigest(),
                            fetch_sha256=hashlib.sha256(image[o-0x148:o+0x30]).hexdigest())

    def test_production_refuses_synthetic_and_wrong_images(self):
        with self.assertRaises(ValidationError):p.compile_patch(self.image)
        with self.assertRaises(ValidationError):p.compile_patch(b'MZ')

    def test_compile_export_reparse_and_idempotence(self):
        with patch.object(p,'PROFILES',(self.profile,)), tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'synthetic.pe';out=Path(tmp)/'test.patch.toml';source.write_bytes(self.image)
            receipt=p.write_patch(source,out);mtime=out.stat().st_mtime_ns
            self.assertEqual(p.write_patch(source,out),receipt)
            self.assertEqual(mtime,out.stat().st_mtime_ns)
            self.assertEqual(receipt['status'],'unwitnessed');self.assertTrue(receipt['toml_reparsed'])
            with self.assertRaises(ValidationError):p.write_patch(source,source)

    def test_occupied_cave_refused_even_with_test_image_hash(self):
        image=bytearray(self.image);image[p.CAVE_START-p.IMAGE_BASE]=1
        profile=replace(self.profile,sha256=hashlib.sha256(image).hexdigest())
        with patch.object(p,'PROFILES',(profile,)),self.assertRaisesRegex(ValidationError,'zero-filled'):
            p.compile_patch(bytes(image))


if __name__=='__main__':
    unittest.main()
