"""V4 human engagement probe, bounded native frames and actual bm disc reads.

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

BM_NAME = ('NFL 2K5 MOD TEST 2026-09-08bm (beta-62 RC86 FINAL CANDIDATE: '
    'Experimental + gameplay opt-ins + MyCareer v4 + read option v3 + kickoff v6 + rim).xiso.iso')
BM = Path(os.environ.get('NFL2K5_READ_OPTION_BM_XISO', str(Path.home() / '2K5 Mod Studio Builds' / BM_NAME)))
BM_XBE_SHA = 'a607da2b454021e078fc51935d62c62280e8f8c679d6ed9c12b583c3658d6f9b'
BM_BOOK_SHA = 'c8eaf4057de5b280b7fd1423fa574c13a3d2bb471167a18a7e9f20b121356cf0'
BM_TABLE_SHA = 'fb0d3d290771ef6f6653dc4f6edc50a6c25de4a3555a47a11f264066d205064c'


def bm_inputs():
    """Read only the XDVDFS directory, 12 MB executable and 78 KB MIN entry."""
    from nfl_uniform_color_xiso_direct_patch import parse_xdvdfs
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    with BM.open('rb') as stream:
        entries, _ = parse_xdvdfs(stream.fileno(), BM.stat().st_size)
        entry = entries['default.xbe']
        if not 0 < entry.size <= 12_300_288:
            raise ValueError('bm XBE exceeds bounded evidence size')
        stream.seek(entry.byte_offset)
        payload = stream.read(entry.size)
    with OuterImage(BM) as archive:
        entry_min = archive.entries[BOOK_ENTRIES['MIN']]
        if entry_min.size != 78_768:
            raise ValueError('bm MIN is not the fixed-size PLAY resource')
        resource = archive.read_entry(entry_min.index)
    if hashlib.sha256(payload).hexdigest() != BM_XBE_SHA or hashlib.sha256(resource).hexdigest() != BM_BOOK_SHA:
        raise unittest.SkipTest('bm evidence differs from the pinned Noah-played XBE/MIN resource')
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
    def test_normal_template_byte_identity_and_both_fixed_budgets(self):
        self.assertEqual(hashlib.sha256(read.assembly.CODE).hexdigest(),
                         '0e1568e44d27d258d44294e285ca5c891ecfbe95b8fe75e65ed1a892d9018c47')
        self.assertLessEqual(len(read.assembly.DIAGNOSTIC_CODE), read.CODE_SIZE)
        self.assertEqual(len(read.PROMPT), len(read.DIAGNOSTIC_PROMPT))
        self.assertEqual(read.DIAGNOSTIC_FIELDS['text']+96, read.DATA_SIZE)
        self.assertIn('CPU reads give', read.DIAGNOSTIC_HELP_TEXT)

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
        self.assertEqual(read.read_settings(self.normal)['model_version'], 3)
        self.assertEqual(read.read_settings(self.diagnostic)['model_version'], 4)
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
        self.assertEqual(fields['read_option_runtime_settings']['model_version'], 4)
        self.assertTrue(fields['read_option_runtime_settings']['diagnostic'])
        self.assertIs(read.apply, original)
        self.assertEqual(read.apply(self.retail)[0], self.normal)

    def test_mixed_variant_hook_prefix_code_and_state_refuse(self):
        image = XbeImage(self.diagnostic)
        places = read.allocations(self.diagnostic)
        for va, byte in ((read.HOOKS['hud'][0]+1, None),
                        (places['read_only']['va']+64, read.PROMPT[0]),
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
        if os.environ.get('NFL2K5_READ_OPTION_V4_TRACE'):
            Path(os.environ['NFL2K5_READ_OPTION_V4_TRACE']).write_text(
                json.dumps(dict(pairing=cls.pairing, observations=cls.evidence), indent=2)+'\n')

    def machine(self, **kwargs):
        gc.collect()
        return DiagnosticMachine(self.payload, self.resource, **kwargs)

    def test_snap_identity_is_independent_of_fixture_condition_node(self):
        for node in (255, 0, 1, 2):
            m = self.machine(controller=0)
            m.uc.mem_write(m.qs+0x450, bytes([node]))
            m.snap_read()
            state = m.diagnostic_hud()
            self.assertEqual(state['text'], 'READ 155 snap 0 0.00')
            self.assertEqual(state['samples'], 0)
            self.assertEqual(state['snap_descriptor'], m.get(m.interp))
            self.assertNotEqual(state['snap_lookup_row'], 0)

    def test_no_snap_no_line_hud_unavailable_and_reset_are_distinct(self):
        m = self.machine(controller=0)
        m.run(0x1AD9C0)
        self.assertEqual(m.diagnostic_hud()['text'], '')
        self.assertEqual(m.snapshot()['hud_calls'], 1)
        self.assertEqual(m.snapshot()['snap_seen'], 0)
        m.snap_read()
        state = m.diagnostic_hud()
        self.assertEqual((state['snap_seen'], state['hud_calls'], state['text_calls']), (1, 1, 0))
        self.assertEqual(state['font_pointer'], 0)
        self.assertEqual(state['text'], 'READ 155 snap 0 0.00')
        m.frame(.05, held=False)
        m.run(0x1AD9C0)
        self.assertEqual(m.snapshot()['snap_seen'], 0)
        self.assertEqual(m.diagnostic_hud()['text'], '')

    def test_diagnostic_can_observe_missing_state_before_live_dispatch(self):
        for member in (0xC, 0x20):
            m = self.machine(controller=0)
            m.u32(0xE602B8, 13)
            m.u32(m.QB+member, 0)
            m.run(0x21516A, ebp=m.QB, stop_at=0x215170)
            self.assertEqual(m.snapshot()['dispatch_calls'], 1)
            if member == 0x20:
                m.snap_read()
                self.assertEqual(m.diagnostic_hud()['text'].rstrip(), 'READ miss ???')

    def test_lookup_misses_names_scripts_and_pointer_copies_fail_closed(self):
        for change in ('unpaired index', 'book', 'name', 'qb script', 'back script', 'copy'):
            m = self.machine(controller=0)
            descriptor = m.get(m.interp)
            if change == 'unpaired index':
                m.u32(m.interp, m.base+0x3404+154*96)
            elif change == 'copy':
                # A copied descriptor outside the native PLAY pools is an
                # explicit rejected hypothesis, never accepted by name alone.
                m.uc.mem_write(m.QB+0xF00, bytes(m.uc.mem_read(descriptor, 96)))
                m.u32(m.interp, m.QB+0xF00)
            else:
                at = {'book': m.get(m.base+0x30), 'name': m.get(descriptor-8),
                      'qb script': m.get(descriptor+4), 'back script': m.get(descriptor+84)}[change]
                m.uc.mem_write(at, bytes([m.uc.mem_read(at, 1)[0] ^ 1]))
            m.snap_read()
            state = m.diagnostic_hud()
            self.assertEqual(state['lookup_row'], 0)
            self.assertEqual(state['text'].rstrip(), 'READ miss '+
                ('???' if change == 'copy' else '154' if change == 'unpaired index' else '155'))
            self.assertEqual(state['condition_calls'], 0)
            self.evidence.append(dict(case=change, state=state))

    def test_full_frames_human_decisions_match_normal_v3_and_retain_photograph_line(self):
        for rpo in (False, True):
            for choice in ('give', 'keep', *(('pass',) if rpo else ())):
                states = []
                traces = []
                for payload in (self.normal, self.payload):
                    gc.collect()
                    m = DiagnosticMachine(payload, self.resource, rpo=rpo, controller=0)
                    for t in (.05, .30, .55, .8, 1.0, 1.05):
                        m.frame(t, held=choice != 'give', throw=choice == 'pass' and t == .30, stick=1)
                    traces.append([{k:v for k,v in row.items() if k != 'edge'} for row in m.trace])
                    if payload is self.payload:
                        state = m.diagnostic_hud()
                        self.assertEqual(state['text'], f'READ {m.pi} {choice} 6 1.05')
                        self.assertEqual(state['dispatch_calls'], 6)
                        self.assertEqual(state['raw_held'], 0 if choice == 'give' else 0x100)
                        self.assertEqual(state['input_throttle'], 1)
                        states.append(state)
                        if choice == 'give':
                            m.exchange(stick=1)
                            self.assertEqual(m.get(m.BALL), m.RB)
                            # Task disposal does not invalidate the photo text.
                            self.assertIn(' give ', m.diagnostic_hud()['text'])
                        elif choice == 'pass':
                            self.assertEqual(m.get(m.QB+0x11C), 0x42)
                        else:
                            self.assertEqual(m.get(m.BALL), m.QB)
                self.assertEqual(traces[0], traces[1])
                self.evidence.append(dict(case=choice, play=157 if rpo else 155, states=states, trace=traces[1]))

    def test_pending_samples_deadline_duplicate_clock_and_raw_input_observation(self):
        m = self.machine(controller=2, layout=1, rpo=True)
        for t in (.05, .20, .40): m.frame(t, held=True, throw=t == .40, stick=1)
        state = m.diagnostic_hud()
        self.assertEqual(state['text'], 'READ 157 pend 3 1.05')
        self.assertEqual((state['raw_held'], state['raw_pressed'], state['input_context'],
                          state['controller_layout'], state['dispatch_controller']), (0x100, 0x200, 8, 1, 2))
        self.assertEqual(state['dispatch_callback'], 0x1AEF80)
        self.assertEqual(state['dispatch_node'], 2)
        self.assertEqual(state['input_command'], 22)
        m.frame(.40, held=False)
        self.assertEqual(m.diagnostic_hud()['samples'], 3)
        self.assertEqual(m.snapshot()['condition_calls'], 4)
        self.evidence.append(dict(case='pending input observation', state=state))

    def test_cpu_probe_defaults_give_and_has_no_edge_cue(self):
        for rpo in (False, True):
            m = self.machine(rpo=rpo)
            for t in (.05, .3, .6, .9, 1.05): m.frame(t)
            self.assertEqual(m.get(m.task+0x44), 1)
            self.assertEqual(m.get(m.state_va+40), 0)
            self.assertIn('give', m.diagnostic_hud()['text'])

    def test_full_unsigned_sample_count_and_unknown_index_fit_owned_text(self):
        m = self.machine(controller=0)
        m.frame(.05, held=False)
        # Format stress inputs only, not a fabricated engagement replay.
        m.u32(m.state_va+20, 0xFFFFFFFF)
        state = m.diagnostic_hud()
        self.assertEqual(state['text'], 'READ 155 pend 4294967295 1.05')
        self.assertLess(len(state['text']), 48)
        for address, size in m.writes:
            if m.state_va <= address < m.state_va+read.DATA_SIZE:
                self.assertLessEqual(address+size, m.state_va+read.DATA_SIZE)

    def test_real_native_font_glyphs_shared_object_and_cpu_state_preserved(self):
        if not (EXTRACT / 'vc_53450030/0').is_file():
            self.skipTest('retail FONT archive absent')
        from nfl2k5_scorebug_projection import read_fonts
        font = read_fonts(EXTRACT / 'vc_53450030/0')[3]
        m = self.machine(controller=0)
        m.resident_font(font)
        before = bytes(m.uc.mem_read(0xA95040, 128))
        m.frame(.05, held=False)
        m.uc.reg_write(x86.UC_X86_REG_XMM0, 0xFEDCBA9876543210)
        m.uc.reg_write(x86.UC_X86_REG_FPCW, 0xB7F)
        state = m.diagnostic_hud()
        self.assertEqual(len(m.draws), 1)
        self.assertEqual(m.draws[0]['text'], state['text'])
        self.assertEqual(m.draws[0]['xy'], (32, 64))
        self.assertGreater(len(m.vertices), 40)
        self.assertIn(0x46DF0, m.hits)
        self.assertEqual(bytes(m.uc.mem_read(0xA95040, 128)), before)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_XMM0), 0xFEDCBA9876543210)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPCW), 0xB7F)
        self.assertEqual((state['hud_calls'], state['text_calls']), (1, 1))
        self.evidence.append(dict(case='native FONT4 glyph submission', font=font.name,
            state=state, vertices=len(m.vertices), draws=m.draws))

    def test_font_path_composes_with_adjacent_widescreen_and_team_column_owners(self):
        from mod_editor.core import nfl2k5_widescreen as wide, nfl2k5_team_column as team
        from nfl2k5_scorebug_projection import read_fonts
        if not (EXTRACT / 'vc_53450030/0').is_file():
            self.skipTest('retail archive containing FONT4 absent')
        font = read_fonts(EXTRACT / 'vc_53450030/0')[3]
        after = team.apply(wide.apply(self.retail)[0])[0]
        after = read.apply(after, intent_table=self.table, diagnostic=True)[0]
        before = team.apply(wide.apply(self.payload)[0])[0]
        self.assertEqual(before, after)
        m = DiagnosticMachine(after, self.resource, controller=0)
        m.resident_font(font)
        m.frame(.05, held=False)
        state = m.diagnostic_hud()
        self.assertEqual(state['text'], 'READ 155 pend 1 1.05')
        self.assertEqual(len(m.vertices), 192)
        self.assertEqual(m.draws[0]['xy'], (32, 64))
        self.assertEqual(read.status(after), 'applied')
        self.assertEqual(wide.status(after), 'applied')
        self.assertEqual(team.status(after), 'applied')


@unittest.skipUnless(uc is not None and XBE.is_file() and BM.is_file(),
    'Unicorn, retail XBE and Noah-played bm disc required; set NFL2K5_READ_OPTION_BM_XISO')
class DiscIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload, cls.resource, cls.table = bm_inputs()

    def test_actual_disc_installed_identity_and_relocated_loader_both_buffers(self):
        self.assertEqual(read.status(self.payload), 'applied')
        self.assertFalse(read.read_settings(self.payload)['diagnostic'])
        self.assertEqual(hashlib.sha256(self.table).hexdigest(), BM_TABLE_SHA)
        fixture, table, receipt = final_reads()
        self.assertNotEqual(fixture, self.resource)
        self.assertEqual(table, self.table)
        for buffer in (0, 1):
            for rpo in (False, True):
                gc.collect()
                m = FrameMachine(self.payload, self.resource, buffer=buffer, rpo=rpo, controller=0)
                code = read.allocations(self.payload)['code']['va']
                row = m.run(code+read.assembly.LABELS['lookup'], esi=m.QB)
                expected = next(r for r in receipt['records'] if r['play_index'] == m.pi)
                self.assertEqual(bytes(m.uc.mem_read(row, 24)).hex(), expected['record'])
                self.assertEqual(m.get(m.interp), m.base+0x3404+m.pi*96)
                # The disc's exact instructions, not a freshly compiled pack,
                # also execute the old post-snap frame fixture successfully.
                self.assertEqual(m.frame(.05, held=False, stick=1)['read_updates'], 1)

    def test_new_diagnostic_on_exact_bm_book_has_human_pending_and_give(self):
        payload = read.apply(XBE.read_bytes(), intent_table=self.table, diagnostic=True)[0]
        for buffer in (0, 1):
            for rpo in (False, True):
                gc.collect()
                m = DiagnosticMachine(payload, self.resource, buffer=buffer, rpo=rpo, controller=0)
                self.assertIn(' snap ', m.diagnostic_hud()['text'])
                m.frame(.05, held=False, stick=1)
                self.assertEqual(m.diagnostic_hud()['text'], f'READ {m.pi} pend 1 1.05')
                m.frame(1.05, held=False, stick=1)
                self.assertEqual(m.diagnostic_hud()['text'], f'READ {m.pi} give 2 1.05')

    def test_native_assignment_producer_keeps_disc_descriptor_pointer(self):
        # Execute the retail assignment selector, then its complete pointer
        # store/node initialization prefix. Team selection is an explicit
        # input; the fixture does not claim to execute the play-call menus.
        for buffer in (0, 1):
            for rpo in (False, True):
                gc.collect()
                m = DiagnosticMachine(self.payload, self.resource, buffer=buffer, rpo=rpo, controller=0)
                selected_play = m.base+0x33FC+m.pi*96
                selection = m.OFF+0x100
                m.u32(selection+12, selected_play)
                m.u32(selection+16, selected_play)
                # Visibility, animation transition and movement-vector reset
                # do not select the descriptor. Their ABIs are the boundaries.
                m.boundaries.update({0x237C40: (0, None), 0x28A050: (0, 0),
                                     0x20F1E0: (0, None)})
                m.u32(m.interp, 0)
                m.run(0x1CEAC0, ecx=m.OFF, edx=0, stop_at=0x1CE600, count=50000)
                descriptor = m.uc.reg_read(x86.UC_X86_REG_EAX)
                self.assertEqual(descriptor, selected_play+8)
                sp = m.uc.reg_read(x86.UC_X86_REG_ESP)
                self.assertEqual((m.get(sp+4), m.get(sp+8)), (m.QB, m.interp))
                m.run(0x1CE600, eax=descriptor, args=(m.QB, m.interp, 0, 0), stop_at=0x1CE642)
                self.assertEqual(m.get(m.interp), descriptor)
                self.assertEqual(m.get(m.qs+0x450) & 255, 255)
                self.assertIn(0x1B8790, m.hits)
                self.assertIn(0x1B84E0, m.hits)


if __name__ == '__main__':
    unittest.main()
