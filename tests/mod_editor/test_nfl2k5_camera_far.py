"""Far selection: public fail-closed fixture and bounded private USA CPU proofs."""
from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_camera as c
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_bump_strength as strength
from tests.mod_editor.test_nfl2k5_xbe_space import synthetic as space_fixture
from tests.mod_editor import test_nfl2k5_widescreen_polish as wide_fixture

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
    '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'
try:
    import unicorn as u
    from unicorn import x86_const as r
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    u = r = Cs = None


def repin(buf):
    for s in strength._sections(buf):
        buf[s.header_offset+36:s.header_offset+56] = strength.section_digest(buf, s)
    return bytes(buf)


def fixture():
    """12 MB maximum: allocator header fixture with three invented mapped spans."""
    buf = bytearray(space_fixture())
    for at, va in space.DEBUG_POINTERS:
        struct.pack_into('<I', buf, at, va)
    struct.pack_into('<II', buf, 0x178, 0x10994, 1)
    for index in range(21):
        off = space.TABLE + index * 56
        if index == 0:
            flags, va, raw, size = 0x16, 0x11000, 0x1000, 0x300000
        elif index == 1:
            flags, va, raw, size = 3, 0x4E3AE0, 0x301000, 0x30000
        elif index == 3:
            flags, va, raw, size = 3, 0xA69980, 0x331000, 0x20000
        else:
            flags, va, raw, size = 3, 0xC00000 + index*0x1000, 0x400000+index*0x1000, 4
        struct.pack_into('<5I', buf, off, flags, va, size, raw, size)
    spans = [(va, before) for va, before in c.HOOKS.values()] + list(c.CONTEXT_PINS)
    spans += [(va, c.RETAIL_DESCRIPTORS[s]) for s, va in c.STANDARD_DESCRIPTORS.items()]
    spans += [(va, c.FAR_RETAIL_DESCRIPTORS[s]) for s, va in c.FAR_DESCRIPTORS.items()]
    document = json.loads((ROOT / 'tests/fixtures/nfl2k5_camera_context.v2.json').read_text())
    spans += [(int(row['va'], 0), bytes.fromhex(row['bytes'])) for row in document['spans']]
    for va, raw in spans:
        off = c._offset(buf, va)
        buf[off:off+len(raw)] = raw
    return repin(buf)


class CameraPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = fixture()
        from mod_editor.core import nfl2k5_depth_chart_storage as special
        cls.pins = ExitStack()
        cls.addClassCleanup(cls.pins.close)
        for module, name, value in (
            (space, "DEBUG_SHA256", space._sha(cls.retail[space.DEBUG_START:space.DEBUG_END])),
            (space, "LIB_SHA256", space._sha(cls.retail[space.LIB_START:space.LIB_END])),
            (space, "METADATA_SHA256", space._sha(cls.retail[space.META_START:space.META_END])),
            (space, "GEOMETRY_SHA256", space._sha(b"".join(cls.retail[space.TABLE+i*56:space.TABLE+i*56+36] for i in range(22)))),
            (special, "RETAIL_CONTENT_SHA256", space._sha(bytes(special.RETAIL_SIZE))),
        ):
            cls.pins.enter_context(patch.object(module, name, value))
        cls.patched, cls.receipt = c.apply(cls.retail)

    def test_replay_exact_receipts_and_only_seven_far_recipients(self):
        self.assertEqual(c.status(self.retail), 'retail')
        self.assertEqual(c.status(self.patched), 'applied')
        self.assertEqual(c.detect_preset(self.patched), 'far_look')
        again, receipt = c.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt['changed_bytes'], 0)
        self.assertTrue(receipt['experimental'])
        self.assertFalse(receipt['runtime_witnessed'])
        self.assertEqual(c.option_default_status(again), 'far')
        self.assertEqual(c.read_standard(again), c.read_standard(self.retail))
        self.assertEqual(c.read_preset_table(again), c.read_preset_table(self.retail))
        self.assertEqual(len(self.receipt['edits']), 14)
        for edit in self.receipt['edits']:
            off, size = int(edit['file_offset'], 0), edit['size']
            self.assertEqual(again[off:off+size], bytes.fromhex(edit['after']))
            self.assertEqual(hashlib.sha256(again[off:off+size]).hexdigest(), edit['after_sha256'])
        for state, row in c.read_far(again).items():
            expected = c.PRESETS[c.DEFAULT_PRESET][state]
            self.assertEqual((row['target'], row['fov'], row['offset']), expected)
            before = c.FAR_RETAIL_DESCRIPTORS[state]
            after = c._read(again, c.FAR_DESCRIPTORS[state], 80)
            for start, end in ((0,16),(28,32),(36,48),(60,80)):
                self.assertEqual(before[start:end], after[start:end])
        for s in strength._sections(again):
            self.assertEqual(again[s.header_offset+36:s.header_offset+56], strength.section_digest(again,s))

    def test_every_partial_install_foreign_context_and_old_version_refuses(self):
        # Allocate first so only this owner's sites vary, with valid digests.
        allocated = space.apply(self.retail, c.REQUESTS, scaleout=True)[0]
        for label, off, before, after in c._sites(allocated, c.DEFAULT_PRESET):
            for base, value in ((allocated, after), (self.patched, before)):
                with self.subTest(label=label, base_applied=base is self.patched):
                    buf = bytearray(base); buf[off:off+len(value)] = value
                    mixed = repin(buf)
                    self.assertEqual(c.status(mixed), 'foreign')
                    with self.assertRaises(c.CameraPatchError): c.apply(mixed)
        for va, pin in c.CONTEXT_PINS:
            buf = bytearray(self.retail); buf[c._offset(buf,va)] ^= 1
            with self.assertRaises(c.CameraPatchError): c.apply(repin(buf))
        buf = bytearray(self.retail)
        for state, va in c.STANDARD_DESCRIPTORS.items():
            off = c._offset(buf,va)
            buf[off:off+80] = c.descriptor_bytes(c.RETAIL_DESCRIPTORS[state],c.FAR_RETAIL_VALUES[state])
        with self.assertRaises(c.CameraPatchError): c.apply(repin(buf))
        self.assertEqual(c.status(b'bad'), 'foreign')

    def test_named_variant_is_exact_and_cannot_mix(self):
        p, _ = c.apply(self.retail, 'broadcast_wide')
        self.assertEqual(c.detect_preset(p), 'broadcast_wide')
        self.assertEqual(c.apply(p,'broadcast_wide')[0],p)
        with self.assertRaises(c.CameraPatchError): c.apply(p)

    def test_sealed_union_without_camera_refuses(self):
        allocated = space.apply(self.retail,(('other','code',16,16),),scaleout=True)[0]
        with self.assertRaisesRegex(c.CameraPatchError,'sealed owner union'): c.apply(allocated)


@unittest.skipUnless(XBE.is_file() and u is not None, 'private USA XBE, Capstone or Unicorn absent')
class SelectionProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size != 11948032:
            raise unittest.SkipTest('expected the 11,948,032-byte pinned USA XBE')
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != '73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9':
            raise unittest.SkipTest('private XBE is not the pinned USA executable')
        cls.patched, cls.receipt = c.apply(cls.retail)
        cls.alloc = c.allocation(cls.patched)

    def machine(self, payload=None):
        helper = wide_fixture.RetailExecutionTests()
        uc = helper.load(self.patched if payload is None else payload)
        # The existing renderer fixture maps retail only; add the owned pages.
        if payload is None:
            for region in space.layout(self.patched)['regions']:
                uc.mem_map(region['va'], region['size'])
                uc.mem_write(region['va'],self.patched[region['raw']:region['raw']+region['size']])
                if region['kind'].startswith('code'):
                    uc.mem_protect(region['va'],region['size'],u.UC_PROT_READ|u.UC_PROT_EXEC)
        return helper, uc

    @staticmethod
    def put(uc,va,*values): uc.mem_write(va,struct.pack('<'+'I'*len(values),*values))
    @staticmethod
    def get(uc,va): return struct.unpack('<I',uc.mem_read(va,4))[0]

    def stub(self, uc, mapping):
        """Only declared peripheral calls are stubbed; wrappers/setters run native."""
        def intercept(machine, address, size, _):
            if address not in mapping: return
            value, pop = mapping[address]
            sp = machine.reg_read(r.UC_X86_REG_ESP)
            self.put(machine,wide_fixture.RetailExecutionTests.AUX,address)
            machine.reg_write(r.UC_X86_REG_EAX,value)
            machine.reg_write(r.UC_X86_REG_EIP,self.get(machine,sp))
            machine.reg_write(r.UC_X86_REG_ESP,sp+4+pop)
        return uc.hook_add(u.UC_HOOK_CODE,intercept)

    def test_fresh_default_preserves_other_settings(self):
        for payload, expected in ((self.retail,0),(self.patched,1)):
            h,uc = self.machine(payload)
            # Execute the full initializer; stub unrelated settings/audio helpers.
            targets = {}
            for i in Cs(CS_ARCH_X86,CS_MODE_32).disasm(c._read(payload,0xE3B90,0x228),0xE3B90):
                if i.mnemonic == 'call': targets[int(i.op_str,0)] = (0,4 if int(i.op_str,0)==0xE3120 else 0)
            self.stub(uc,targets)
            h.execute(uc,0xE3B90)
            self.assertEqual(self.get(uc,c.OPTION_GLOBAL_VA),expected)
            self.assertEqual(tuple(self.get(uc,c.OPTION_GLOBAL_VA+n) for n in (4,8,12,16,20,24)),
                             (1,0,0,0x3F800000,0x3F000000,0x42C80000))

    def test_saved_settings_import_overrides_only_index_and_preserves_source(self):
        h,uc = self.machine()
        for selected in (0,1,2,3,4,5,6,7,0xFFFFFFFF):
            original = bytearray((i*13+7)%256 for i in range(0x2e0))
            struct.pack_into('<I',original,0x70,selected)
            uc.mem_write(h.SRC,bytes(original))
            expected = bytearray(original); struct.pack_into('<I',expected,0x70,1)
            for call in (0x16D1D4,0x16E7B1,0x16E864):
                h.execute(uc,call,ecx=h.SRC,at_call=True,stop=call+5)
                self.assertEqual(bytes(uc.mem_read(0xE5FF80,0x2e0)),bytes(expected))
                self.assertEqual(bytes(uc.mem_read(h.SRC,0x2e0)),bytes(original))
                self.assertEqual(uc.reg_read(r.UC_X86_REG_EAX),0xE5FF80)
                self.assertEqual(uc.reg_read(r.UC_X86_REG_ESP),h.STACK)
            # Replay/temporary settings restores must retain the session choice.
            h.execute(uc,0xE2E20,ecx=h.SRC)
            self.assertEqual(bytes(uc.mem_read(0xE5FF80,0x2e0)),bytes(original))

    def test_game_entry_resets_all_modes_then_options_and_frames_keep_session_choice(self):
        h,uc = self.machine()
        stubs = {0x771F0:(1,0),0xE3B20:(0,0),0x626A0:(0,0),0x5E1B0:(0,0),
                 0x5F460:(0,0),0x91390:(0,0),0xAC420:(0,0),0xABF60:(0,0),
                 0xA5620:(0,4),0x2C6800:(0,0),0x5F710:(0,0),0x627C0:(0,0),
                 0xA54F0:(0,0)}
        self.stub(uc,stubs)
        for mode in range(10):
            for old in range(8):
                self.put(uc,0xE5FF80,mode);self.put(uc,c.OPTION_GLOBAL_VA,old)
                self.put(uc,0xB665F0,old);self.put(uc,0xB665E0,1)
                # Actual common game-entry call, through the full camera init.
                # Only its peripheral reset/random-camera helpers are stubbed.
                h.execute(uc,0x64991,at_call=True,stop=0x64996)
                self.assertEqual((self.get(uc,c.OPTION_GLOBAL_VA),self.get(uc,0xB665F0)),(1,1))
            for choice in range(6):
                self.put(uc,0xB616C0,0)
                h.execute(uc,0x2C6960,ecx=choice,edx=1)
                h.execute(uc,0xA5490)
                self.assertEqual((self.get(uc,c.OPTION_GLOBAL_VA),self.get(uc,0xB665F0)),(choice,choice))
            # Next new game discards the previous session choice.
            h.execute(uc,0xA55EB)
            self.assertEqual(self.get(uc,0xB665F0),1)
        stubs[0x771F0] = (0,0)
        self.put(uc,0xB665F0,7);self.put(uc,c.OPTION_GLOBAL_VA,1)
        h.execute(uc,0xA5490)
        self.assertEqual(self.get(uc,0xB665F0),1)

    def test_native_active_row_indexes_the_far_recipients(self):
        h,uc = self.machine()
        self.put(uc,0xE5FFF4,1,0,0)
        table=c.read_preset_table(self.patched)
        for row in (c.STANDARD_ROW,c.FAR_ROW):
            for state in c.FAR_DESCRIPTORS:
                # Execute the actual table indexing and call to the native
                # descriptor copier/setup. Stop before moving-player focus.
                self.put(uc,0xB665F0,row)
                uc.reg_write(r.UC_X86_REG_EAX,self.get(uc,0xB665F0))
                uc.reg_write(r.UC_X86_REG_ESI,state)
                uc.reg_write(r.UC_X86_REG_EBX,0x3F800000)
                h.execute(uc,0xA572D,stop=0xA5741)
                copied=bytes(uc.mem_read(0xA82D30,80))
                self.assertEqual(copied,c._read(self.patched,table[row][state][1],80))
                if row==c.FAR_ROW:
                    self.assertEqual(table[row][state][1],c.FAR_DESCRIPTORS[state])

    def test_native_geometry_clearance_and_widescreen_y_invariance(self):
        from tools.nfl2k5_camera_far_proof import prove
        proof = prove(self.retail)
        self.assertEqual(len(proof['rows']),54)
        reference = {}
        for row in proof['rows']:
            self.assertGreater(row['focus_clearance_px'],110)
            self.assertGreater(row['backfield_clearance_px'],60)
            key=(row['state'],row['direction'],row['pass_zoom'],row['pullback'])
            y=[point[1] for point in row['points_640x480'].values()]
            if row['aspect']=='4:3': reference[key]=y
            else:
                for before,after in zip(reference[key],y): self.assertAlmostEqual(before,after,places=3)
        # All three constructors/setup routes have retained the descriptor
        # geometry. The optional pass-zoom callback has its own proved inputs.
        for row in proof['rows']:
            if row['pass_zoom']==0:
                decoded=row['descriptor_after_setup'];expected=c.PRESETS['far_look'][row['state']]
                self.assertEqual((decoded['target'],decoded['fov'],decoded['offset']),expected)

    def test_mycareer_uses_options_for_the_session_when_camera_patch_is_selected(self):
        from mod_editor.core import nfl2k5_my_career as career
        from tests.nfl2k5_my_career_fixture import Machine, prepared
        save,setup,_=prepared()
        seed=space.apply(self.retail,c.REQUESTS+career.REQUESTS,scaleout=True)[0]
        first=c.apply(career.apply(seed,setup=setup)[0])[0]
        second=career.apply(c.apply(seed)[0],setup=setup)[0]
        self.assertEqual(first,second)
        machine=Machine(first,save,career.read_setup(setup))
        machine.activate()
        machine.stub(0x771F0,lambda:machine.ret(1))
        machine.stub(0xA5620,lambda:machine.ret(pop=4))
        machine.stub(0x2C6800,lambda:machine.ret())
        machine.put(0xB665F0,0)
        machine.call(0xA55EB)
        self.assertEqual(machine.get(0xB665F0),1)
        for choice in range(6):
            machine.put(0xB616C0,0)
            machine.call(0x2C6960,ecx=choice,edx=1)
            machine.call(0xA5490)
            self.assertEqual(machine.get(0xB665F0),choice)

    def test_buildplan_existing_camera_flag_produces_the_same_xbe(self):
        from mod_editor.core import mod_build
        with tempfile.TemporaryDirectory(prefix='camera-far-') as temp:
            directory=Path(temp).resolve()
            source=directory/'default.xbe';target=directory/'camera.xbe'
            source.write_bytes(self.retail)
            receipt=mod_build.build(mod_build.BuildPlan(str(source),str(target),camera=True,
                name='Far selection',notes='EXPERIMENTAL / UNWITNESSED'))
            self.assertEqual(target.read_bytes(),self.patched)
            self.assertEqual(source.read_bytes(),self.retail)
            self.assertEqual(receipt['steps'][0]['camera'],'applied')
            self.assertEqual(mod_build.inspect(target)['camera'],'applied')



if __name__ == '__main__': unittest.main()
