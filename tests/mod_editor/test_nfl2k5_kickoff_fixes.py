"""A-D bounded regressions; private fixtures are read-only and <13 MB.

Animation clip installation/rendering and final GPU submission are test doubles;
retail eligibility, heading, idle selection and world line geometry execute.
"""
from pathlib import Path
import hashlib
import struct
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_nfl2k5_dynamic_kickoff import Machine, RETAIL, PRIVATE_REASON, uni, x86, Cs
from mod_editor.core import nfl2k5_dynamic_kickoff as dk, nfl2k5_kick_rules as kr
from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated, nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_kickoff_returns as returns, nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_widescreen as wide
from mod_editor.core.nfl2k5_bump_strength import RETAIL_XBE_SHA256
from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource, RESOURCE_HEADER_SIZE, NODE_BASE
from tools import nfl2k5_kickoff_alignment as alignment


class RecognitionTests(unittest.TestCase):
    def test_short_or_foreign_resource_is_reported_without_throwing(self):
        for raw in (b'', b'PLAY', bytes(0x133B0)):
            self.assertEqual(returns.status(raw), 'foreign')


@unittest.skipUnless(RETAIL.is_file() and uni is not None and Cs is not None, PRIVATE_REASON + '; unicorn/capstone required')
class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_XBE_SHA256:
            raise unittest.SkipTest('private retail XBE SHA-256 differs')
        cls.base = kr.apply(cls.retail)[0]
        cls.fixed = dk.apply(cls.base)[0]
        cls.grown = relocated.apply(space.apply(cls.fixed, relocated.REQUESTS)[0])[0]

    def variants(self):
        yield self.fixed, dk.FLAGS
        _, data = relocated._sites(self.grown)
        yield self.grown, data['va']

    def test_ball_inside_one_is_not_touchback_even_with_retail_animation_override(self):
        for direction in (-1, 1):
            for payload, state in [(self.base, dk.FLAGS), *self.variants()]:
                m = Machine(payload, direction=direction, state_va=state)
                if payload != self.base:
                    m.launch()
                team = m.RECEIVE_TEAM
                m.put(team + 0x110, team + 0x240)
                z0, z1 = sorted((direction * 4572, direction * 5486.4))
                m.uc.mem_write(team + 0x240, struct.pack('<4f', -2438.4, z0, 2438.4, z1))
                for yards in (1, .5, .01, 0, -.01):
                    m.position(0, direction * (4572 - yards * 91.44), m.RETURNER)
                    m.f32(m.RETURNER + 0xB38, direction * (4572 - yards * 91.44))
                    m.put(m.RETURNER + 0x904, 0x5103A0)
                    m.uc.reg_write(x86.UC_X86_REG_EDI, m.RETURNER)
                    m.run(0xB6760)
                    self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX),
                                     0 if payload != self.base and yards > 0 else 1,
                                     (direction, yards, state))
                    self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK + 4)

    def test_touchback_guard_preserves_retail_outside_its_scope(self):
        for payload, state in self.variants():
            for case in ('safety', 'scrimmage', 'ready', 'inactive', 'loose', 'other_holder', 'sideline', 'short'):
                m = Machine(payload, state_va=state)
                m.launch()
                team = m.RECEIVE_TEAM
                m.put(team + 0x110, team + 0x240)
                m.uc.mem_write(team + 0x240, struct.pack('<4f', -2438.4, 4572, 2438.4, 5486.4))
                m.put(m.RETURNER + 0x904, 0x5103A0)
                m.f32(m.RETURNER + 0xB38, 4480.56)
                m.position(2500 if case == 'sideline' else 0,
                           2600 if case == 'short' else 4480.56,
                           0 if case == 'loose' else m.KICKER if case == 'other_holder' else m.RETURNER)
                if case in ('safety', 'scrimmage'):
                    m.put(dk.PHASE, 1 if case == 'safety' else 4)
                if case == 'ready': m.put(dk.PLAY_STATE, 13)
                if case == 'inactive': m.uc.mem_write(state, b'\0')
                m.uc.reg_write(x86.UC_X86_REG_EDI, m.RETURNER)
                m.run(0xB6760)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 1, case)

    def test_idle_selection_heading_root_hold_and_release_both_allocations(self):
        for payload, state in self.variants():
            for direction in (-1, 1):
                m = Machine(payload, direction=direction, state_va=state)
                m.launch()
                for who, sign in ((m.COVERAGE, direction), (m.BLOCKER, -direction)):
                    m.f32(who + 0x110, 1)  # stale running input
                    m.put(who + 0x118, 2)  # stale turning mode
                    for offset in (0x90C, 0x910, 0xC28, 0xB50):
                        m.put(who + offset, 0x4000)  # sideways previous frame
                    m.f32(who + 0xB30, 123)
                    m.f32(who + 0xB38, 456)
                    m.sampler_displacement = 9000
                    for frame in range(3):
                        before = m.get(m.COUNTER)
                        m.run(dk.HOOKS['plan'][0], ecx=who)
                        self.assertEqual(m.get(m.COUNTER), before)
                        m.run(dk.HOOKS['motion'][0], esi=who)
                        self.assertEqual(m.get(m.COUNTER), before + 1)
                        self.assertEqual(m.get(who + 0x904), 0x50F4EC)
                        self.assertEqual(m.get(who + 0x91C), who + 0xDC0)
                        self.assertEqual(m.clips[-1], (who, who + 0xDF0))
                        self.assertEqual(m.readf(who + 0x110), 0)
                        for offset in (0x114, 0x90C, 0xC28, 0xB50):
                            self.assertEqual(m.get(who + offset), 0 if sign > 0 else 0x8000)
                        self.assertEqual(m.readf(who + 0xB30), 123)
                        self.assertEqual(m.readf(who + 0xB38), 456)
                        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK + 4)
                m.position(0, direction * 3600)
                m.event('ground')
                old = m.get(m.COUNTER)
                m.run(dk.HOOKS['plan'][0], ecx=m.COVERAGE)
                self.assertEqual(m.get(m.COUNTER), old + 1)

    def test_return_block_nodes_decode_into_local_drive_and_lead_initializers(self):
        from mod_editor.core import nfl2k5_play_codec as codec
        for direction in (-1, 1):
            for kind in (0, 4):
                m = Machine(self.fixed, direction=direction)
                who, decoded = m.BLOCKER, 0x2018000
                operands = [kind, 0, 1, 0, 2, 0, 0, 0]
                node = codec.Node(0x11, 6 if kind == 0 else 3, operands).to_bytes()
                m.run(0x2B5D60, ecx=decoded, edx=int.from_bytes(node[4:], 'little'))
                values = [m.readf(decoded + i * 12 + 4) for i in range(8)]
                self.assertEqual(values, operands)
                # Populate the engine's evaluated operand cache from its real
                # decoder. The opcode queries and initializer execute unchanged.
                m.uc.mem_write(m.OPS, node)
                for i, value in enumerate(values):
                    m.f32(who + 0x61C + 0x14 + i * 4, value)
                m.run(0x2400B0, ecx=who, stop=0x23F450)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EDX), kind)
                sp = m.uc.reg_read(x86.UC_X86_REG_ESP)
                self.assertEqual([m.get(sp + 4 + i * 4) for i in range(6)],
                                 [0, 0, 1, 0, 0, 0x8000])
                # Real target anchoring and selector-mode dispatch. Existing
                # opponent history/stance setup are stubs, not the selector.
                m.put(who + 0x510, m.SCALAR)
                m.put(0xE6029C, m.GAME)
                m.f32(m.GAME + 0x10, 1)
                m.f32(who + 0xB30, 400)
                m.f32(who + 0xB38, direction * 3000)
                m.stub_pops.update({0x239C10: 0, 0x23ABA0: 0, 0x2C9AB0: 0,
                                    0x239C40: 4, 0x23A3E0: 12})
                m.uc.emu_start(0x23F450, 0x2FAFF0, count=30000)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EIP), 0x2FAFF0)
                sp = m.uc.reg_read(x86.UC_X86_REG_ESP)
                self.assertEqual(m.get(sp + 8), 2 if kind == 0 else 3)
                anchor = m.uc.reg_read(x86.UC_X86_REG_EDX)
                self.assertEqual(m.readf(anchor), 400)
                self.assertEqual(m.readf(anchor + 8), direction * 3000)

    def test_world_route_line_uses_world_vertices_unchanged_by_widescreen(self):
        outputs = []
        for payload in (self.fixed, wide.apply(self.fixed)[0]):
            m = Machine(payload)
            m.put(0xBDFBE4, 0)  # 75D90 -> 1807F0 on-field mode
            points = (m.CONTACT, m.CONTACT + 16)
            m.uc.mem_write(points[0], struct.pack('<8f', 1000, 5, 914.4, 1, 1000, 5, 1371.6, 1))
            before = bytes(m.uc.mem_read(points[0], 32))
            m.run(0x180120, args=(points[0],))
            self.assertEqual(bytes(m.uc.mem_read(points[0], 32)), before)
            vertices, projected = [], []
            def capture(uc, address, size, data):
                if address == 0x2AB40:
                    projected.append(address)
                if address == 0x164880:
                    sp = uc.reg_read(x86.UC_X86_REG_ESP)
                    ptrs = (m.get(sp + 4), m.get(sp + 8), uc.reg_read(x86.UC_X86_REG_ESI), uc.reg_read(x86.UC_X86_REG_EDI))
                    vertices.extend(struct.unpack('<4f', uc.mem_read(p, 16)) for p in ptrs)
                    m._ret(8)  # final GPU submission only
            m.uc.hook_add(uni.UC_HOOK_CODE, capture)
            m.run(0x164AC0, ecx=points[0], edx=points[1])
            self.assertFalse(projected)
            self.assertEqual(len(vertices), 4)
            self.assertAlmostEqual(sum(v[0] for v in vertices) / 4, 1000, places=3)
            self.assertTrue(all(abs(v[1] - 5) < .001 for v in vertices))
            outputs.append(vertices)
        self.assertEqual(*outputs)


@unittest.skipUnless((RETAIL.parent / 'vc_53450030').is_dir(), 'private extracted PLAY archive required')
class ReturnDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.books = []
        with alignment.recode.OuterImage(RETAIL.parent / 'vc_53450030') as archive:
            for book, _ in alignment._load(archive):
                cls.books.append((book.name, archive.read_entry(book.entry_index)))

    def test_all_36_books_private_chains_idempotence_receipts_and_untouched_other_plays(self):
        self.assertEqual(len(self.books), 36)
        for name, raw in self.books:
            with self.subTest(book=name):
                self.assertEqual(returns.status(raw), 'retail')
                out, receipt = returns.apply(raw)
                self.assertEqual(len(raw), len(out))
                self.assertEqual(receipt['nodes_added'], 78)
                self.assertEqual(returns.apply(out)[0], out)
                replay = bytearray(raw)
                for edit in receipt['edits']:
                    offset = edit['offset']; before = bytes.fromhex(edit['before']); after = bytes.fromhex(edit['after'])
                    self.assertEqual(raw[offset:offset + len(before)], before)
                    replay[offset:offset + len(after)] = after
                self.assertEqual(replay, out)
                changed = {p['index'] for p in receipt['plays']}
                oldbody, body = raw[32:], out[32:]
                parsed = parse_playbook_resource(raw)
                for p in parsed.plays:
                    if p.index not in changed:
                        self.assertEqual(lib.play_chains(oldbody, p.index), lib.play_chains(body, p.index))
                for p in changed:
                    old, new = lib.play_chains(oldbody, p)[1], lib.play_chains(body, p)[1]
                    for slot in range(2):
                        self.assertEqual(old[slot][1][:3], new[slot][1][:3])
                    for slot in range(11):
                        from mod_editor.core.nfl2k5_play_codec import Node
                        block = Node.from_bytes(new[slot][1][-1])
                        self.assertEqual((block.op, block.operands), (0x11, [0, 0, 1, 0, 2, 0, 0, 0]))
                    for slot in range(2, 11):
                        self.assertEqual([n[0] for n in new[slot][1]], [1, 0x11])

    def test_previous_lead_branch_is_refused_before_mutation(self):
        import json
        prior = json.loads((Path(__file__).resolve().parents[2] / 'docs/nfl2k5_kickoff_fixes_receipts.json').read_text())
        receipts = {r['name']: r for r in prior['books']}
        for name, raw in self.books:
            old = bytearray(raw)
            for edit in receipts[name]['edits']:
                start = edit['offset']; after = bytes.fromhex(edit['after'])
                old[start:start + len(after)] = after
            self.assertEqual(hashlib.sha256(old).hexdigest(), receipts[name]['replacement_sha256'])
            self.assertEqual(returns.status(old), 'foreign')
            before = bytes(old)
            with self.assertRaisesRegex(ValueError, 'mixed/foreign'):
                returns.apply(old)
            self.assertEqual(old, before)

    def test_v2_receipts_replay_alignment_then_returns_in_all_books(self):
        import json
        path = Path(__file__).resolve().parents[2] / 'docs/nfl2k5_kickoff_v2_receipts.json'
        receipts = {row['name']: row for row in json.loads(path.read_text())['books']}
        self.assertEqual(set(receipts), {name for name, _ in self.books})
        for name, raw in self.books:
            receipt = receipts[name]
            self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt['retail_sha256'])
            aligned = bytearray(raw)
            for edit in receipt['alignment_edits']:
                start = edit['offset']; after = bytes.fromhex(edit['after'])
                self.assertEqual(raw[start:start + len(after)].hex(), edit['before'])
                aligned[start:start + len(after)] = after
            self.assertEqual(hashlib.sha256(aligned).hexdigest(), receipt['source_sha256'])
            expected = returns.apply(bytes(aligned))[0]
            replay = bytearray(aligned)
            for edit in receipt['edits']:
                start = edit['offset']; after = bytes.fromhex(edit['after'])
                self.assertEqual(aligned[start:start + len(after)].hex(), edit['before'])
                replay[start:start + len(after)] = after
            self.assertEqual(bytes(replay), expected)
            self.assertEqual(hashlib.sha256(replay).hexdigest(), receipt['replacement_sha256'])

    def test_archive_writer_validates_all_books_before_writing_and_repeats(self):
        from tools import nfl2k5_kickoff_returns as tool
        source = [raw for _name, raw in self.books[:2]]
        books = [SimpleNamespace(name=name, entry_index=i, virtual_offset=(i + 1) * 0x20000)
                 for i, (name, _raw) in enumerate(self.books[:2])]
        class Archive:
            def __init__(self, payloads):
                self.payloads = [bytearray(p) for p in payloads]
                self.writes = []
            def __enter__(self): return self
            def __exit__(self, *exc): pass
            def read_entry(self, i): return bytes(self.payloads[i])
            def read(self, offset, size):
                i = offset // 0x20000 - 1
                start = offset - books[i].virtual_offset
                return bytes(self.payloads[i][start:start + size])
            def write(self, offset, data):
                i = offset // 0x20000 - 1
                start = offset - books[i].virtual_offset
                self.payloads[i][start:start + len(data)] = data
                self.writes.append(offset)
        archive = Archive(source)
        with patch.object(alignment.recode, 'OuterImage', return_value=archive), patch.object(alignment, '_load', return_value=[(b, {}) for b in books]):
            receipt = tool.apply('bounded fixture')
            self.assertEqual(receipt['books'], 2)
            self.assertGreater(receipt['changed_bytes'], 0)
            for i, raw in enumerate(source):
                self.assertEqual(archive.payloads[i], returns.apply(raw)[0])
            count = len(archive.writes)
            self.assertEqual(tool.apply('bounded fixture')['changed_bytes'], 0)
            self.assertEqual(len(archive.writes), count)
            # A partially patched input is refused before any write.
            archive.payloads[0] = bytearray(source[0])
            with self.assertRaisesRegex(ValueError, 'mixed'):
                tool.apply('bounded fixture')
            self.assertEqual(len(archive.writes), count)

    def test_foreign_and_partial_chains_refused_without_changing_source(self):
        raw = self.books[0][1]
        out, _ = returns.apply(raw)
        parsed, rows, _ = returns._inspect(out)
        p = rows[0][0]
        # Corrupt an appended deep Start, preserving the rest of the resource.
        start = parsed.decoded_play(p.index)[0]['start']
        bad = bytearray(out)
        bad[32 + NODE_BASE + start * 8 + 4] ^= 1
        frozen = bytes(bad)
        self.assertEqual(returns.status(frozen), 'foreign')
        with self.assertRaises(ValueError): returns.apply(frozen)
        self.assertEqual(bytes(bad), frozen)


if __name__ == '__main__':
    unittest.main()
