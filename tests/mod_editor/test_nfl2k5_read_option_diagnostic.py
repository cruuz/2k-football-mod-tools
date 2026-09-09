"""V5 resolved identities, native cancellation, FONT and actual bo disc reads.

No game boot or display. Actor scheduling/poses, controller samples, animation
events and FONT residency are explicit inputs, never a live-engagement claim.
"""
from __future__ import annotations

import gc
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_read_option_runtime as read
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_read_option_runtime import XBE, EXTRACT, repin
from tests.mod_editor.test_nfl2k5_read_option_frames import FrameMachine, final_reads
from tests.mod_editor.test_nfl2k5_read_option_unicorn import uc, x86

BO_NAME = ('NFL 2K5 MOD TEST 2026-09-08bo (beta-63 DIAGNOSTIC: Experimental + gameplay opt-ins + read option v4 HUD probe).xiso.iso')
BO = Path(os.environ.get('NFL2K5_READ_OPTION_BO_XISO', str(Path.home() / '2K5 Mod Studio Builds' / BO_NAME)))
BO_XBE_SHA = '18c467fbed452f358d059766bebb424b87068da432aa9f002c132235c2bc6d10'
BO_BOOK_SHA = 'c8eaf4057de5b280b7fd1423fa574c13a3d2bb471167a18a7e9f20b121356cf0'
BO_TABLE_SHA = 'fb0d3d290771ef6f6653dc4f6edc50a6c25de4a3555a47a11f264066d205064c'


def bo_inputs():
    """Read only the XDVDFS directory, 12 MB executable and 78 KB MIN entry."""
    from nfl_uniform_color_xiso_direct_patch import parse_xdvdfs
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    with BO.open('rb') as stream:
        entries, _ = parse_xdvdfs(stream.fileno(), BO.stat().st_size)
        entry = entries['default.xbe']
        if not 0 < entry.size <= 12_300_288:
            raise ValueError('bo XBE exceeds bounded evidence size')
        stream.seek(entry.byte_offset)
        payload = stream.read(entry.size)
    with OuterImage(BO) as archive:
        entry_min = archive.entries[BOOK_ENTRIES['MIN']]
        if entry_min.size != 78_768:
            raise ValueError('bo MIN is not the fixed-size PLAY resource')
        resource = archive.read_entry(entry_min.index)
    if hashlib.sha256(payload).hexdigest() != BO_XBE_SHA or hashlib.sha256(resource).hexdigest() != BO_BOOK_SHA:
        raise unittest.SkipTest('bo evidence differs from the pinned Noah-played XBE/MIN resource')
    places = read.allocations(payload)
    table = XbeImage(payload).read(places['read_only']['va'], read.TABLE_SIZE)
    return payload, resource, table


class DiagnosticMachine(FrameMachine):
    def __init__(self, *args, **kwargs):
        self.draws, self.vertices = [], []
        super().__init__(*args, **kwargs)

    def observe(self, u, address, size, user):
        if address == 0x47420:
            obj = u.reg_read(x86.UC_X86_REG_ECX)
            at = u.reg_read(x86.UC_X86_REG_EDX)
            text = bytes(u.mem_read(at, 96)).decode('utf-16le').split('\0', 1)[0]
            self.draws.append(dict(text=text, object=obj,
                xy=struct.unpack('<2f', u.mem_read(obj+16, 8))))
        elif address == 0x2CA70:
            self.vertices.append(struct.unpack('<4f', u.mem_read(u.reg_read(x86.UC_X86_REG_ECX), 16)))
        super().observe(u, address, size, user)

    def snapshot(self):
        return read.decode_diagnostic_state(bytes(self.uc.mem_read(self.state_va, read.DATA_SIZE)))

    def diagnostic_hud(self):
        self.draws, self.vertices = [], []
        self.boundaries.update({0x2D2A0: (12, None), 0x2CB90: (8, None),
            0x2CBE0: (0, None), 0x2CA70: (0, None), 0x2CA00: (0, None)})
        self.run(0x646A1, stop_at=0x646A6, count=100000)
        return self.snapshot()

    def resident_font(self, font):
        # Bounded, parser-certified host relocation of the real FONT4 resource.
        # This explicitly supplies residency; it does not prove live HUD setup.
        at = 0x3080000
        if len(font.decoded) > 0x70000:
            raise AssertionError('FONT fixture exceeds its arena')
        self.uc.mem_write(at, font.decoded)
        obj = at + font.object_offset
        self.u32(obj+8, at+font.range_offset)
        for row in font.ranges:
            self.u32(at+row['record_offset']+4, at+row['glyph_records_offset'])
        self.run(0x46920, ecx=0xA95040)
        self.run(0x469B0, ecx=0xA95040, edx=obj)
        self.run(0x46B60, ecx=0xA95040, edx=2)
        self.run(0x46A00, ecx=0xA95040, edx=3)


class FormatContractTests(unittest.TestCase):
    def test_both_fixed_budgets_and_diagnostic_cpu_policy(self):
        self.assertLessEqual(len(read.assembly.CODE),read.CODE_SIZE)
        self.assertLessEqual(len(read.assembly.DIAGNOSTIC_CODE),read.CODE_SIZE)
        self.assertEqual((read.CODE_SIZE,read.DATA_SIZE,read.RO_SIZE),(2048,256,88))
        self.assertEqual(len(read.PROMPT),len(read.DIAGNOSTIC_PROMPT))
        self.assertIn('CPU reads give',read.DIAGNOSTIC_HELP_TEXT)

    def test_memory_decoder_is_bounded_and_does_not_claim_display_evidence(self):
        result = read.decode_diagnostic_state(bytes(256))
        self.assertEqual((result['phase'], result['text']), ('off', ''))
        self.assertFalse(result['runtime_witnessed'])
        for invalid in (b'', bytes(255), bytes(257), None):
            with self.assertRaises(ValueError): read.decode_diagnostic_state(invalid)
        nonfinite = bytearray(256)
        struct.pack_into('<I', nonfinite, 44, 0x7FC00000)
        self.assertEqual(read.decode_diagnostic_state(bytes(nonfinite))['deadline'], 'nan')


@unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE required')
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('local XBE differs from pinned USA evidence')
        cls.normal = read.apply(cls.retail)[0]
        cls.diagnostic, cls.receipt = read.apply(cls.retail, diagnostic=True)

    def test_explicit_variant_and_idempotent_rebuild_contract(self):
        self.assertEqual(read.read_settings(self.normal)['model_version'], 5)
        self.assertEqual(read.read_settings(self.diagnostic)['model_version'], 5)
        self.assertEqual(read.read_settings(self.diagnostic)['authored_reads'], 0)
        self.assertIs(read.apply(self.diagnostic)[0], self.diagnostic)
        self.assertEqual(read.apply(self.diagnostic, diagnostic=True)[1]['changed_bytes'], 0)
        for payload, mode in ((self.normal, True), (self.diagnostic, False)):
            with self.assertRaisesRegex(ValueError, 'rebuild'): read.apply(payload, diagnostic=mode)
        with self.assertRaisesRegex(ValueError, 'Boolean'): read.apply(self.retail, diagnostic=1)
        self.assertEqual(self.receipt['changed_bytes'],
            sum(a != b for a, b in zip(self.retail, self.diagnostic)) + len(self.diagnostic)-len(self.retail))

    def test_changed_native_font_dependency_refuses_before_mutation(self):
        for va, _, _ in read.DIAGNOSTIC_GUARDS:
            for source in (self.retail, self.diagnostic):
                bad = bytearray(source)
                bad[XbeImage(source).offset(va)] ^= 1
                bad = repin(bad)
                before = hashlib.sha256(bad).digest()
                with self.assertRaisesRegex(ValueError, 'diagnostic dependency'):
                    read.apply(bad, diagnostic=True)
                self.assertEqual(hashlib.sha256(bad).digest(), before)

    def test_scoped_build_adapter_selects_diagnostic_and_publishes_real_settings(self):
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        original = read.apply
        table = read.compile_intent_table()[0]

        def instrumented(payload, **kwargs):
            return original(payload, diagnostic=True, **kwargs)

        with patch.object(read, 'apply', instrumented):
            output, receipt = tuning._read_option_adapter(table).apply(self.retail)
        self.assertEqual(output, self.diagnostic)
        self.assertTrue(receipt['diagnostic'])
        fields = tuning._grown_status_fields(output)
        self.assertEqual(fields['read_option_runtime'], 'applied')
        self.assertEqual(fields['read_option_runtime_settings']['model_version'], 5)
        self.assertTrue(fields['read_option_runtime_settings']['diagnostic'])
        self.assertIs(read.apply, original)
        self.assertEqual(read.apply(self.retail)[0], self.normal)

    def test_mixed_variant_hook_prefix_code_and_state_refuse(self):
        image = XbeImage(self.diagnostic)
        places = read.allocations(self.diagnostic)
        for va, byte in ((read.HOOKS['hud'][0]+1, None),
                        (places['read_only']['va']+68, read.PROMPT[4]),
                        (places['code']['va']+1900, None),
                        (places['data']['va']+208, None)):
            bad = bytearray(self.diagnostic)
            offset = image.offset(va)
            bad[offset] = bad[offset] ^ 1 if byte is None else byte
            bad = repin(bad)
            self.assertEqual(read.status(bad), 'foreign')
            with self.assertRaises(ValueError): read.apply(bad)


@unittest.skipUnless(uc is not None and XBE.is_file(), 'Unicorn and pinned USA retail XBE required')
class DiagnosticFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('local XBE differs from pinned USA evidence')
        cls.resource, cls.table, cls.pairing = final_reads()
        cls.payload = read.apply(cls.retail, intent_table=cls.table, diagnostic=True)[0]
        cls.normal = read.apply(cls.retail, intent_table=cls.table)[0]
        cls.evidence = []

    @classmethod
    def tearDownClass(cls):
        if os.environ.get('NFL2K5_READ_OPTION_V5_TRACE'):
            Path(os.environ['NFL2K5_READ_OPTION_V5_TRACE']).write_text(
                json.dumps(dict(pairing=cls.pairing, observations=cls.evidence), indent=2)+'\n')

    def machine(self, **kwargs):
        gc.collect()
        return DiagnosticMachine(self.payload, self.resource, **kwargs)

    def test_snap_and_pending_lines_are_resolved_resource_numbers(self):
        for rpo in (False,True):
            for node in (255,0,1,2):
                m=self.machine(controller=0,rpo=rpo)
                m.uc.mem_write(m.qs+0x450,bytes([node]));m.snap_read()
                state=m.diagnostic_hud()
                self.assertEqual(state['text'],f'READ {m.pi} snap')
                self.assertEqual(state['native_play_index'],m.pi)
                self.assertEqual(state['descriptor'],m.get(m.interp))
                self.assertNotEqual(state['lookup_row'],0)
        m=self.machine(controller=0);m.frame(.05)
        self.assertEqual(m.diagnostic_hud()['text'],'READ 155 pend')
        m.exchange();self.assertEqual(m.diagnostic_hud()['text'],'READ 155 give')

    def test_reset_empty_table_and_foreign_book_names_scripts_are_distinct(self):
        m=self.machine(controller=0);m.run(0x1AD9C0)
        self.assertEqual(m.diagnostic_hud()['text'],'')
        for change in ('index','book','name','qb','back','copy'):
            m=self.machine(controller=0);descriptor=m.get(m.interp)
            if change=='index':m.u32(m.interp,m.base+0x3404+48*96)
            elif change=='copy':
                m.uc.mem_write(m.QB+0xF00,bytes(m.uc.mem_read(descriptor,88)))
                m.u32(m.interp,m.QB+0xF00)
            else:
                at={'book':m.get(m.base+0x30),'name':m.get(descriptor-8),
                    'qb':m.get(descriptor+4),'back':m.get(descriptor+84)}[change]
                m.uc.mem_write(at,bytes([m.uc.mem_read(at,1)[0]^1]))
            m.snap_read();state=m.diagnostic_hud()
            self.assertEqual(state['lookup_row'],0)
            self.assertEqual(state['text'],'READ miss '+('48' if change=='index' else '???' if change=='copy' else '155'))
        empty=read.apply(self.retail,diagnostic=True)[0]
        m=DiagnosticMachine(empty,self.resource,controller=0)
        self.assertEqual(m.diagnostic_hud()['text'],'READ miss 155')

    def test_reordered_live_record_resolves_source_number_without_offset_guess(self):
        m=self.machine(controller=0)
        old=m.base+0x33FC+155*96;new=m.base+0x33FC+48*96
        a=bytes(m.uc.mem_read(old,96));b=bytes(m.uc.mem_read(new,96))
        m.uc.mem_write(old,b);m.uc.mem_write(new,a)
        m.u32(m.interp,new+8);m.u32(m.RB+0xA1C,new+88)
        m.snap_read();state=m.diagnostic_hud()
        self.assertEqual((state['play_index'],state['native_play_index']),(155,48))
        self.assertEqual(state['text'],'READ 155 snap')
        self.assertEqual(m.frame(.05)['decision'],0xFFFFFFFF)
        self.assertEqual(m.diagnostic_hud()['text'],'READ 155 pend')
        self.evidence.append(dict(case='synthetic reorder, not the live 48 explanation',state=state))

    def test_normal_and_diagnostic_human_frames_agree_on_every_control(self):
        for rpo in (False,True):
            for name,press in [('keep',0x100),('pitch',0x1000)]+([('pass',0x400)] if rpo else []):
                traces=[]
                for payload in (self.normal,self.payload):
                    gc.collect();m=DiagnosticMachine(payload,self.resource,controller=0,rpo=rpo)
                    m.frame(.05);m.exchange(deliver=False);m.frame(.25,press=press)
                    traces.append(m.trace)
                    if payload is self.payload:
                        state=m.diagnostic_hud()
                        self.assertEqual(state['text'],f'READ {m.pi} {name}')
                        self.assertEqual(state['raw_pressed'],press)
                        self.evidence.append(dict(case=name,state=state,trace=m.trace))
                self.assertEqual(traces[0],traces[1])

    def test_cpu_diagnostic_gives_and_duplicate_clock_does_not_consume_press(self):
        m=self.machine();m.frame(.05);m.frame(.15);m.frame(.25)
        self.assertEqual(m.get(m.state_va+28),0xFFFFFFFF)
        self.assertEqual(m.get(m.state_va+40),0)
        m.frame(1.1);self.assertEqual(m.diagnostic_hud()['text'],'READ 155 give')
        m=self.machine(controller=2);m.frame(.05);m.frame(.05,press=0x1000)
        state=m.diagnostic_hud();self.assertEqual((state['samples'],state['raw_pressed']),(1,0))

    def test_native_font_glyphs_preserve_shared_font_and_float_state(self):
        if not (EXTRACT/'vc_53450030/0').is_file():self.skipTest('retail FONT archive absent')
        from nfl2k5_scorebug_projection import read_fonts
        font=read_fonts(EXTRACT/'vc_53450030/0')[3]
        m=self.machine(controller=0);m.resident_font(font)
        before=bytes(m.uc.mem_read(0xA95040,128));m.frame(.05)
        m.uc.reg_write(x86.UC_X86_REG_XMM0,0xFEDCBA9876543210)
        m.uc.reg_write(x86.UC_X86_REG_FPCW,0xB7F)
        state=m.diagnostic_hud()
        self.assertEqual(len(m.draws),1);self.assertEqual(m.draws[0]['text'].rstrip(),state['text'])
        self.assertEqual(m.draws[0]['xy'],(32,64));self.assertGreater(len(m.vertices),32)
        self.assertIn(0x46DF0,m.hits);self.assertEqual(bytes(m.uc.mem_read(0xA95040,128)),before)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_XMM0),0xFEDCBA9876543210)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPCW),0xB7F)
        self.evidence.append(dict(case='retail FONT4 glyph submission',state=state,draws=m.draws,vertices=len(m.vertices)))

    def test_font_path_composes_with_widescreen_and_team_columns(self):
        from mod_editor.core import nfl2k5_widescreen as wide,nfl2k5_team_column as team
        before=team.apply(wide.apply(self.payload)[0])[0]
        after=read.apply(team.apply(wide.apply(self.retail)[0])[0],intent_table=self.table,diagnostic=True)[0]
        self.assertEqual(before,after)
        self.assertEqual(read.status(after),'applied')


@unittest.skipUnless(uc is not None and XBE.is_file() and BO.is_file(),
    'Unicorn, retail XBE and Noah-played bo disc required; set NFL2K5_READ_OPTION_BO_XISO')
class DiscIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_payload,cls.resource,cls.table=bo_inputs()
        cls.payload=read.apply(XBE.read_bytes(),intent_table=cls.table,diagnostic=True)[0]

    def test_exact_bo_v4_number_can_be_overwritten_by_another_slot_zero_actor(self):
        from tests.mod_editor.test_nfl2k5_qb_spy_unicorn import Machine
        m = Machine(self.old_payload, patched=False)
        base = m.load_book(self.resource)
        places = read.allocations(self.old_payload)
        state = places['data']['va']
        # Offset 1625 is the v4 diagnostic lookup in the pinned bo executable.
        # The whole bo XBE hash is checked by bo_inputs before this executes.
        lookup = places['code']['va'] + 1625
        for actor, pi in ((m.QB, 155), (m.OTHER, 48)):
            m.uc.mem_write(actor+0x2E, b'\0')
            m.uc.mem_write(actor+0xA50, b'\x02')
            m.u32(actor+0xA1C, base+0x3404+pi*96)
        m.u32(state+56, m.QB)  # snap actor, deliberately different from OTHER
        m.run(lookup, esi=m.QB)
        self.assertEqual(m.get(state+60), 155)
        self.assertNotEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 0)
        m.run(lookup, esi=m.OTHER)
        self.assertEqual(m.get(state+60), 48)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 0)
        self.assertEqual(m.get(state+56), m.QB)

    def test_bo_loader_and_native_menu_keep_resource_numbers_in_both_heaps(self):
        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource,FORMATION_BASE,FORMATION_SIZE
        book=parse_playbook_resource(self.resource,asset_id='book:MIN')
        self.assertEqual(book.plays[48].name,'PA Z Slant')
        self.assertEqual(book.plays[155].name,'SD Zone Read EXPERIMENTAL')
        self.assertEqual(book.plays[157].name,'SD RPO EXPERIMENTAL')
        self.assertEqual(hashlib.sha256(self.table).hexdigest(),BO_TABLE_SHA)
        self.assertEqual(final_reads()[1],self.table)
        self.assertEqual(read.status(self.old_payload),'foreign')
        formation=next(f for f in book.formations if f.name=='I Jokers')
        for buffer in (0,1):
            gc.collect();m=DiagnosticMachine(self.payload,self.resource,buffer=buffer,controller=0)
            for link in formation.play_links:
                # Native menu accessor takes the formation pointer and menu
                # ordinal, and returns book+0x60+96*(link & 0x1ff).
                pi=link.play_index
                ptr=m.run(0xE13F0,ecx=m.base,edx=formation.play_links.index(link),
                    args=(m.base+FORMATION_BASE+formation.index*FORMATION_SIZE,))
                self.assertEqual(ptr,m.base+0x33FC+pi*96)
            m.snap_read();self.assertEqual(m.diagnostic_hud()['text'],'READ 155 snap')
            m.frame(.05);self.assertEqual(m.diagnostic_hud()['text'],'READ 155 pend')
            m.exchange();self.assertEqual(m.diagnostic_hud()['text'],'READ 155 give')

    def test_actual_bo_native_assignment_selector_preserves_selected_descriptor(self):
        for pi in (155,157):
            gc.collect();m=DiagnosticMachine(self.payload,self.resource,controller=0,play_index=pi)
            selected=m.base+0x33FC+pi*96;selection=m.OFF+0x100
            m.u32(selection+12,selected);m.u32(selection+16,selected)
            m.boundaries.update({0x237C40:(0,None),0x28A050:(0,0),0x20F1E0:(0,None)})
            m.u32(m.interp,0)
            m.run(0x1CEAC0,ecx=m.OFF,edx=0,stop_at=0x1CE600,count=50000)
            descriptor=m.uc.reg_read(x86.UC_X86_REG_EAX)
            self.assertEqual(descriptor,selected+8)
            m.run(0x1CE600,eax=descriptor,args=(m.QB,m.interp,0,0),stop_at=0x1CE642)
            self.assertEqual(m.get(m.interp),descriptor)
            self.assertEqual(m.get(m.qs+0x450)&255,255)
            m.snap_read();self.assertEqual(m.diagnostic_hud()['text'],f'READ {pi} snap')

    def test_bo_diagnostic_records_source_rpo_and_gun_predictions(self):
        rows=[]
        for resource,table,pis in ((self.resource,self.table,(155,157)),(*final_reads(shotgun=True)[:2],(134,31))):
            payload=read.apply(XBE.read_bytes(),intent_table=table,diagnostic=True)[0]
            for pi in pis:
                gc.collect();m=DiagnosticMachine(payload,resource,controller=0,play_index=pi)
                m.frame(.05);state=m.diagnostic_hud()
                self.assertEqual((state['native_play_index'],state['text']),(pi,f'READ {pi} pend'))
                rows.append(dict(resource_sha256=hashlib.sha256(resource).hexdigest(),state=state))
        if path:=os.environ.get('NFL2K5_READ_OPTION_V5_IDENTITY'):
            Path(path).write_text(json.dumps(dict(bo_xbe_sha256=BO_XBE_SHA,bo_min_sha256=BO_BOOK_SHA,
                bo_table_sha256=BO_TABLE_SHA,native_48='PA Z Slant',cases=rows,
                live_48_explanation_proved=False),indent=2)+'\n')


if __name__ == '__main__':
    unittest.main()
