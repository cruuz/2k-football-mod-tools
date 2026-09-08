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
        from tests.mod_editor.test_nfl2k5_read_option_frames import FrameMachine
        gc.collect()
        return FrameMachine(payload or self.payload, self.resource, **kwargs)

    def test_blocked_or_removed_authored_edge_selects_snap_replacement(self):
        for missing in (False,True):
            m=self.machine();p=m.second_edge()
            if missing:m.u32(m.DEF+4,p)
            else:m.u32(m.RB+0xE40,m.P)
            m.frame(.05)
            self.assertEqual(m.get(m.state_va+40),p)

    def test_auto_edge_prefers_outer_play_side_rush_and_authored_hint(self):
        auto=patch.apply(self.retail,intent_table=self.auto_table)[0]
        for direction in (-1,1):
            for role in (10,16):
                m=self.machine(payload=auto,direction=direction)
                p=m.second_edge(role=role,x=-2.4*direction)
                m.frame(.05);self.assertEqual(m.get(m.state_va+40),p)
        m=self.machine();m.second_edge(x=-2.4);m.frame(.05)
        self.assertEqual(m.get(m.state_va+40),m.P)

    def test_foreign_roles_assignments_members_and_blocked_candidates_give(self):
        for change in ('dt','deep','coverage','roster','assignment','inactive','blocked','other_side'):
            m=self.machine()
            p=m.second_edge(role=15 if change=='dt' else 10,
                x=2 if change=='other_side' else -2,depth=-5 if change=='deep' else -1,
                rushing=change!='coverage')
            m.u32(m.RB+0xE40,m.P)
            if change=='roster':m.u32(p+0x3C,m.P+0xD00)
            elif change=='assignment':m.u32(p+0xA1C,m.base+0x3404+24)
            elif change=='inactive':m.u32(p+0x48,1)
            elif change=='blocked':m.u32(m.OTHER+0xE40,p)
            m.frame(.05)
            self.assertEqual(m.get(m.state_va+40),0,change)
            self.assertEqual(m.frame(1.1)['decision'],1)

    def test_physical_button_binding_all_controller_slots_and_layouts(self):
        for controller in range(4):
            for layout in range(3):
                for context in (8,10):
                    m=self.machine(controller=controller,layout=layout,context=context,rpo=True)
                    m.frame(.05,held=True);m.frame(.1)
                    self.assertEqual(m.frame(.15,held=True,press=0x100)['decision'],0)
                    self.assertEqual(m.frame(.2,stick=1)['throttle'],1)

    def test_nonfinite_samples_cannot_pull_and_new_play_clears_state(self):
        for value in (float('nan'),float('inf'),-float('inf'),1e20):
            m=self.machine();m.edge(vx=value)
            for t in (.05,.15,.25,1.1):row=m.frame(t)
            self.assertEqual(row['decision'],1)
        m=self.machine(controller=0);m.frame(.05)
        m.run(0x1AD9C0,stop_at=0x1AD9DE)
        self.assertEqual(bytes(m.uc.mem_read(m.state_va,256)),bytes(256))
        self.assertEqual(bytes(m.uc.mem_read(0xBE4E28,88*4)),b'\xff'*(88*4))


if __name__ == '__main__':
    unittest.main()
