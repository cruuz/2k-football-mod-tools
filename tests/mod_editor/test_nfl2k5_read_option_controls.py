"""Read-window/HUD, snap assignments and native RPO handoff, standalone.

The GPU submission, task allocation and aiming-math boundaries are recorded
with their exact ABI. No game loop, contact, transfer or display is simulated.
"""
from __future__ import annotations
import gc
import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_read_option_runtime as patch
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.mod_editor.test_nfl2k5_read_option_runtime import XBE, compiled_reads, repin
from tests.mod_editor.test_nfl2k5_read_option_unicorn import Machine, uc, x86


def shotgun_reads(*, receiver_slot=7):
    from mod_editor.core import nfl2k5_play_library as library
    from mod_editor.core import nfl2k5_formation_play_writer as writer
    from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource
    raw, _ = compiled_reads()
    book = parse_playbook_resource(raw, asset_id='book:MIN')
    formation = next(f for f in book.formations if f.name == 'Gun: Doubles Right')
    defense = next(f.index for f in book.formations if f.name == '4-3')
    requests = []
    for preset, index, name in zip(library.OPTION_PRESETS[1:], (134, 31),
                                   ('SD Gun Zone Read', 'SD Gun RPO Slant')):
        design = library.make_option_design(book, raw[32:], formation.index, preset,
                     opponent_formation_index=defense, read_slot=2, receiver_slot=receiver_slot)
        requests.append(writer.PlayCreateRequest(book.asset_id, design.donor_play_index,
                name, assignments=design.chains, replace_index=index,
                play_flags=design.play_flags, option_intent=design.intent))
    compiled = writer.compile_formation_play_creations(raw, [], requests)
    return raw, compiled


class ControlsMachine(Machine):
    SECOND = 0x3008000

    def __init__(self, *args, **kwargs):
        self.boundaries = {}
        self.submissions = []
        super().__init__(*args, **kwargs)

    def observe(self, u, address, size, user):
        super().observe(u, address, size, user)
        if address not in self.boundaries:
            return
        cleanup, result = self.boundaries[address]
        if result == 'float':
            self.submissions.append((address, ()))
            # Only the aiming result is synthetic; execute fld1/ret4 to obey
            # the actual x87 return convention, then native code continues.
            u.mem_write(self.STOP+0x100, b'\xd9\xe8\xc2\x04\x00')
            u.reg_write(x86.UC_X86_REG_EIP, self.STOP+0x100)
            return
        esp = u.reg_read(x86.UC_X86_REG_ESP)
        args = tuple(self.get(esp+4+i*4) for i in range(cleanup//4))
        self.submissions.append((address, args))
        if result is not None:
            u.reg_write(x86.UC_X86_REG_EAX, result)
        u.reg_write(x86.UC_X86_REG_ESP, esp+4+cleanup)
        u.reg_write(x86.UC_X86_REG_EIP, self.get(esp))

    def second_edge(self, *, role=16, x=-2, depth=-1, rushing=True):
        p = self.SECOND
        self.player(p, self.DEF)
        self.uc.mem_write(p+0x2E, b'\x02')
        self.uc.mem_write(p+0xD35, bytes([role]))
        descriptor = self.base+0x3404+(16 if rushing else self.pi*96)
        self.u32(p+0x600+0x41C, descriptor)
        self.f32(p+0x430, x*91.44)
        self.f32(p+0x438, 1200+depth*91.44)
        self.f32(p+0x440, 4*91.44 if x < 0 else -4*91.44)
        self.u32(self.P+0x34, p)
        self.snap_read()
        return p

    def hud(self, ready=True):
        # Native world-marker queue transport; one EDGE head, no glyph yet.
        # Native projection itself is exercised in the v3 frame suite.
        self.u32(0xA94EA4, 1)
        self.u32(0xA94EAC, self.get(self.P+0x3C))
        self.uc.mem_write(0xA94EB0, struct.pack('<4h', 360, 120, 360, 96))
        self.u32(0xA94EB8, 5 << 21)
        self.u32(0xA94EA0, int(ready))
        self.boundaries = {0x2D2A0: (12, None), 0x2CB90: (8, None),
                           0x2CB50: (12, None), 0x2CA00: (0, None)}
        self.submissions = []
        self.run(0x646A1, stop_at=0x646A6)
        return [args for address, args in self.submissions if address == 0x2CB50]

    def pass_initializer(self):
        # Execute the real native branch advancement and full pass initializer.
        # Allocation boundary leaves this fixture's already owned native task.
        node = self.run(0x1B8A20, ecx=self.interp)
        self.run(0x1B8790, ecx=self.interp, edx=node)
        self.run(0x1B84E0, eax=self.interp)
        self.u32(self.DEF+8, self.OFFMETA)
        self.boundaries = {0x2C9AB0: (0, None), 0x198C20: (4, 'float')}
        return self.run(0x19C740, ecx=self.QB)


@unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE required')
class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('XBE differs from pinned USA evidence')

    def test_v1_request_set_requires_rebuild_and_partial_new_owner_refuses(self):
        old = ((patch.OWNER, 'code', 960, 16), (patch.OWNER, 'read_only', 64, 16))
        for requests in (old, patch.REQUESTS[:2]):
            allocated, _ = space.apply(self.retail, requests, scaleout=True)
            snapshot = hashlib.sha256(allocated).digest()
            self.assertEqual(patch.status(allocated), 'foreign')
            with self.assertRaisesRegex(ValueError, 'allocation|rebuild'):
                patch.apply(allocated)
            self.assertEqual(hashlib.sha256(allocated).digest(), snapshot)

    def test_no_authored_defender_is_explicit_and_preserves_paired_play_identity(self):
        _, compiled = compiled_reads()
        pairs = [(compiled.replacement, compiled.report)]
        table, report = patch.compile_intent_table(pairs, use_authored_edge=False)
        self.assertEqual(patch.validate_intent_table(table), 2)
        self.assertEqual([r['authored_read_slot'] for r in report['records']], [None, None])
        self.assertEqual(table[37], patch.AUTO_EDGE)
        self.assertEqual(table[61], patch.AUTO_EDGE)
        self.assertEqual(report['table_sha256'], hashlib.sha256(table).hexdigest())
        with self.assertRaisesRegex(ValueError, 'Boolean'):
            patch.compile_intent_table(pairs, use_authored_edge=None)

    def test_native_shotgun_reads_preserve_resources_links_and_pairing(self):
        from mod_editor.core import nfl2k5_play_library as library
        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource
        raw, compiled = shotgun_reads()
        self.assertEqual(len(raw), len(compiled.replacement))
        before = parse_playbook_resource(raw, asset_id='book:MIN')
        after = compiled.parsed_replacement
        self.assertEqual(before.formations, after.formations)
        table, report = patch.compile_intent_table([(compiled.replacement, compiled.report)],
                                                   use_authored_edge=False)
        self.assertEqual(patch.validate_intent_table(table), 2)
        self.assertEqual({r['play_index'] for r in report['records']}, {134, 31})
        for formation in before.formations:
            if formation.name in ('Gun: Empty Open', 'Gun: Doubles Right'):
                with self.assertRaises(ValueError):
                    library.make_option_design(before, raw[32:], formation.index, 'Speed option')
        self.assertEqual(before.node_count+59, after.node_count)

    def test_every_new_hook_prompt_and_initial_state_refuse_foreign_bytes(self):
        output, _ = patch.apply(self.retail)
        image = XbeImage(output)
        places = patch.allocations(output)
        addresses = [va for va, _ in patch.HOOKS.values()]
        addresses += [places['data']['va'], places['read_only']['va']+64]
        for address in addresses:
            bad = bytearray(output)
            bad[image.offset(address)] ^= 1
            bad = repin(bad)
            with self.subTest(address=hex(address)):
                self.assertEqual(patch.status(bad), 'foreign')
                with self.assertRaises(ValueError):
                    patch.apply(bad)
        self.assertEqual(patch.apply(output)[1]['changed_bytes'], 0)


@unittest.skipUnless(uc is not None and XBE.is_file(), 'Unicorn and pinned USA retail XBE required')
class ControlsInstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('XBE differs from pinned USA evidence')
        _, compiled = compiled_reads()
        cls.resource = compiled.replacement
        pairs = [(compiled.replacement, compiled.report)]
        cls.table = patch.compile_intent_table(pairs)[0]
        cls.auto_table = patch.compile_intent_table(pairs, use_authored_edge=False)[0]
        cls.payload = patch.apply(cls.retail, intent_table=cls.table)[0]

    def machine(self, *, payload=None, **kwargs):
        gc.collect()
        return ControlsMachine(payload or self.payload, self.resource, **kwargs)

    def test_prompt_uses_native_atlas_draw_only_for_human_during_mesh(self):
        m = self.machine(controller=0)
        self.assertEqual(m.hud(), [])
        m.frames(1)
        vertices = m.hud()
        self.assertEqual(len(vertices), 4)
        self.assertIn(0xFA0B0, m.hits)
        self.assertIn(0xF97F0, m.hits)
        uv = [struct.unpack('<2f', struct.pack('<2I', *args))
              for address, args in m.submissions if address == 0x2CB90]
        self.assertEqual(uv, [(0, 0), (.25, 0), (0, .5), (.25, .5)])
        self.assertEqual(m.hud(ready=False), [])
        m.finish()
        self.assertEqual(m.hud(), [])
        m = self.machine(); m.frames(1)
        self.assertEqual(m.hud(), [])

    def test_prompt_invalidates_on_phase_ownership_task_roster_assignment_and_control_change(self):
        for change in ('phase', 'ball', 'task', 'roster', 'assignment', 'node', 'controller', 'clock'):
            m = self.machine(controller=2)
            m.frames(1)
            self.assertEqual(len(m.hud()), 4)
            if change == 'phase': m.u32(0xE602B8, 15)
            elif change == 'ball': m.u32(m.BALL, m.RB)
            elif change == 'task': m.u32(m.qs+0x310, m.RB+0xE00)
            elif change == 'roster': m.u32(m.QB+0x3C, m.RB+0xD00)
            elif change == 'assignment': m.u32(m.interp, m.get(m.interp)+96)
            elif change == 'node': m.uc.mem_write(m.qs+0x450, b'\x03')
            elif change == 'controller': m.u32(m.QB+0x100, -1)
            else: m.f32(m.GAME+0x410, 1.8)
            with self.subTest(change=change): self.assertEqual(m.hud(), [])

    def test_blocked_or_absent_authored_edge_selects_unblocked_live_replacement(self):
        for missing in (False, True):
            m = self.machine()
            replacement = m.second_edge()
            if missing: m.u32(m.DEF+4, replacement)
            else: m.u32(m.RB+0xE40, m.P)
            m.finish()
            self.assertEqual(m.get(m.task+0x40), replacement)
            self.assertEqual(m.get(m.task+0x44), 0)
            self.assertEqual(m.back_result(), 0)

    def test_auto_edge_chooses_play_side_rushing_end_or_olb_and_preserves_authored_preference(self):
        auto = patch.apply(self.retail, intent_table=self.auto_table)[0]
        for direction in (-1, 1):
            for role in (10, 16):
                m = self.machine(payload=auto, direction=direction)
                p = m.second_edge(role=role, x=-2.4*direction)
                m.frames(1)
                self.assertEqual(m.get(m.task+0x40), p)
        m = self.machine()
        m.second_edge(x=-2.4)
        m.frames(1)
        self.assertEqual(m.get(m.task+0x40), m.P)

    def test_replacement_refuses_interior_deep_coverage_substituted_or_changed_assignment(self):
        for change in ('dt', 'deep', 'coverage', 'roster', 'assignment', 'inactive', 'blocked', 'other_side'):
            m = self.machine()
            p = m.second_edge(role=15 if change == 'dt' else 10,
                              x=2 if change == 'other_side' else -2,
                              depth=-5 if change == 'deep' else -1,
                              rushing=change != 'coverage')
            m.u32(m.RB+0xE40, m.P)
            if change == 'roster': m.u32(p+0x3C, m.P+0xD00)
            elif change == 'assignment': m.u32(p+0x600+0x41C, m.base+0x3404+24)
            elif change == 'inactive': m.u32(p+0x48, 1)
            elif change == 'blocked': m.u32(m.OTHER+0xE40, p)
            m.finish()
            with self.subTest(change=change):
                self.assertEqual(m.get(m.task+0x40), 0)
                self.assertEqual(m.get(m.task+0x44), 1)

    def test_hysteresis_rejects_one_tick_twitch_and_survives_one_wide_sample(self):
        m = self.machine()
        m.edge(vx=0); m.frames(patch.MESH_FRAMES-2)
        m.edge(vx=4); m.frames(1)
        m.edge(vx=0); m.finish()
        self.assertEqual(m.get(m.task+0x44), 1)
        m = self.machine()
        m.frames(patch.MESH_FRAMES-1)
        m.edge(vx=0); m.finish()
        self.assertEqual(m.get(m.task+0x44), 0)
        m = self.machine()
        m.frames(patch.MESH_FRAMES-3)
        m.edge(vx=0); m.finish()
        self.assertEqual(m.get(m.task+0x44), 1)

    def test_clock_duplicates_do_not_sample_and_frame_deadline_ignores_late_input(self):
        m = self.machine(controller=0)
        m.tick(.1)
        for _ in range(5): m.tick(.1, held=False)
        self.assertEqual(m.get(m.state_va+20), 1)
        m.frames(patch.MESH_FRAMES-2)
        m.tick(m.readf(m.state_va+44), held=False)
        self.assertEqual(m.get(m.task+0x44), 0)
        m = self.machine(controller=0)
        m.frames(patch.MESH_FRAMES-2); m.frames(1, held=False); m.finish()
        self.assertEqual(m.get(m.task+0x44), 1)
        m = self.machine(controller=0)
        m.tick(.2); m.tick(.1, held=False)
        self.assertEqual(m.get(m.task+0x44), 0)

    def test_native_snap_and_new_play_clear_all_owned_state_and_preserve_flags(self):
        m = self.machine(controller=0, rpo=True)
        m.frames(1, throw=True)
        m.run(0x1AD9C0, stop_at=0x1AD9DE)
        self.assertEqual(bytes(m.uc.mem_read(m.state_va, patch.DATA_SIZE)), bytes(patch.DATA_SIZE))
        for flags in (0x202, 0x247, 0xA93):
            m.run(0xB6FBD, stop_at=0xB6FC3, eflags=flags)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EFLAGS), flags)
            self.assertEqual(m.get(m.state_va), 0)
            self.assertEqual(m.get(m.state_va+64), m.P)

    def test_shotgun_hold_keep_release_give_and_rpo_native_pass(self):
        _, compiled = shotgun_reads()
        table = patch.compile_intent_table([(compiled.replacement, compiled.report)])[0]
        payload = patch.apply(self.retail, intent_table=table)[0]
        for held, expected in ((True, 0), (False, 1)):
            gc.collect()
            m = ControlsMachine(payload, compiled.replacement, controller=0, play_index=134)
            m.finish(held=held)
            self.assertEqual(m.get(m.task+0x44), expected)
            self.assertEqual(m.back_result(), expected)
        gc.collect()
        m = ControlsMachine(payload, compiled.replacement, controller=0, rpo=True, play_index=31)
        m.frames(1, throw=True); m.finish()
        m.pass_initializer()
        self.assertEqual(m.get(m.task), 0x19BAE0)
        self.assertEqual(m.get(m.task+0x40), m.OTHER)

    def test_shotgun_x_receiver_press_and_unready_target_at_pass_entry(self):
        _, compiled = shotgun_reads(receiver_slot=8)
        table = patch.compile_intent_table([(compiled.replacement, compiled.report)])[0]
        payload = patch.apply(self.retail, intent_table=table)[0]
        for ready in (True, False):
            gc.collect()
            m = ControlsMachine(payload, compiled.replacement, controller=3, layout=2,
                                context=10, rpo=True, play_index=31)
            m.uc.mem_write(m.OTHER+0x2E, b'\x08')
            m.throw_mask = 0x400
            m.frames(1, throw=True); m.finish()
            self.assertEqual(m.get(m.task+0x44), 2)
            m.ready(ready)
            m.pass_initializer()
            self.assertEqual(m.get(m.task), 0x19BAE0 if ready else 0x19BB60)
            self.assertEqual(m.get(m.state_va+32), 0)
            if ready:
                m.uc.mem_write(0xBDFCD0+8*2, b'\x02')
                m.boundaries = {0x198C20: (4, 'float')}
                m.run(m.get(m.task), ecx=m.QB)
                self.assertEqual(m.get(m.QB+0x100+0x1C), 0x43)

    def test_receiver_press_crosses_full_native_pass_initializer(self):
        m = self.machine(controller=1, rpo=True)
        m.frames(1, throw=True)
        m.finish(held=False)
        self.assertEqual(m.get(m.task+0x44), 2)
        self.assertEqual(m.get(m.state_va+32), m.OTHER)
        m.pass_initializer()
        self.assertEqual(m.get(m.task), 0x19BAE0)
        self.assertEqual(m.get(m.task+0x40), m.OTHER)
        self.assertEqual(m.get(m.state_va+32), 0)
        self.assertIn(0x1565F0, m.hits)
        self.assertIn(0x19B800, m.hits)
        # Execute the installed native request callback. Aim calculation is
        # the sole stub; slot lookup, readiness and the native command store run.
        m.uc.mem_write(0xBDFCD0+7*2, b'\x01')
        m.boundaries = {0x198C20: (4, 'float')}
        m.run(m.get(m.task), ecx=m.QB)
        self.assertEqual(m.get(m.QB+0x100+0x1C), 0x42)
        self.assertEqual(m.get(0xBE47C4), 0x3F800000)
        self.assertIn(0x1907D0, m.hits)
        self.assertIn(0x19B800, m.hits)
        self.assertIn(0x199260, m.hits)
        self.assertEqual(m.get(m.BALL), m.QB)
        # A second initializer cannot replay a consumed mesh press.
        m.run(0x19C849, stop_at=0x19C84F, esi=m.task)
        self.assertEqual(m.get(m.task), 0x19BB60)


if __name__ == '__main__':
    unittest.main()
