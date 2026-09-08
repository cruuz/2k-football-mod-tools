"""Bounded native kickoff v2 proofs. No disc/pack is loaded into memory.

CPU execution is not an emulator/gameplay witness. Animation decompression and
final skeletal blending are leaves; native time, root callbacks, target scoring,
assignment initialization and diagram projection execute from the pinned XBE.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_nfl2k5_dynamic_kickoff import Machine, RETAIL, PRIVATE_REASON, uni, x86, Cs
from mod_editor.core import nfl2k5_dynamic_kickoff as dk, nfl2k5_dynamic_kickoff_relocated as relocated
from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_kick_rules as kr
from mod_editor.core import nfl2k5_widescreen as wide, nfl2k5_play_codec as codec
from mod_editor.core.nfl2k5_bump_strength import RETAIL_XBE_SHA256, _sections, section_digest
from tools import nfl2k5_kickoff_alignment as alignment

ROOT = Path(__file__).resolve().parents[2]


def previous_payload(retail):
    """Replay the committed v1 receipt, not an approximation of the old hook."""
    result = bytearray(kr.apply(retail)[0])
    for edit in json.loads((ROOT / 'docs/nfl2k5_kickoff_fixes_receipts.json').read_text())['legacy']['edits']:
        after = bytes.fromhex(edit['after'])
        result[edit['offset']:edit['offset'] + len(after)] = after
    for section in _sections(result):
        result[section.header_offset + 36:section.header_offset + 56] = section_digest(result, section)
    return bytes(result)


def v2_payload(base):
    """Keep the played v2 executable reproducible after the v3 compiler change."""
    receipt = json.loads((ROOT / 'docs/nfl2k5_kickoff_v2_receipts.json').read_text())
    result = bytearray(base)
    for edit in receipt['legacy']['edits'] + receipt['legacy_section_digest_edits']:
        after = bytes.fromhex(edit['after'])
        result[edit['offset']:edit['offset'] + len(after)] = after
    if hashlib.sha256(result).hexdigest() != receipt['legacy_output_sha256']:
        raise AssertionError('historical v2 receipt no longer replays exactly')
    return bytes(result)


class NativeMachine(Machine):
    def __init__(self, *args, **kwargs):
        self.samples = []
        self.trace = []
        self.watch_player = 0
        self.root_writes = []
        super().__init__(*args, **kwargs)
        self.uc.mem_map(0x2020000, 0x30000)
        self.put(0xE6029C, self.GAME)
        self.f32(self.GAME + 0x10, 1)
        self.uc.mem_write(self.CALLBACK + 0x70, b'\xdd\xd8\xc3')
        for who in (self.KICKER, self.RETURNER, self.COVERAGE, self.BLOCKER):
            self.put(who + 0x510, who + 0x150)  # native empty task-stack sentinel
        self.uc.hook_add(uni.UC_HOOK_MEM_INVALID, self._invalid)
        self.write_hook = self.uc.hook_add(uni.UC_HOOK_MEM_WRITE, self._write)

    def _write(self, uc, access, address, size, value, data):
        if self.watch_player:
            start = self.get(self.watch_player + 0x18) + 0x30
            if start <= address < start + 48:
                old = int.from_bytes(uc.mem_read(address, size), 'little')
                if old != value:
                    self.root_writes.append((uc.reg_read(x86.UC_X86_REG_EIP), address - start, old, value))

    def _invalid(self, uc, access, address, size, value, data):
        raise AssertionError(f'Unmapped access {access} {address:#x}, PC={uc.reg_read(x86.UC_X86_REG_EIP):#x}')

    def animation(self, who):
        # Three root keys, no events, one bone. The native clock and root
        # interpolator run. Bone decompression/blending terminate at their ABI.
        channels = 0x2040000 + (who - self.KICKER) // 4
        clip = channels + 0x100
        self.put(who + 0xDC4, clip)
        self.uc.mem_write(clip, struct.pack('<BBH', 1, 0, 3))
        self.put(clip + 4, 1)  # looping
        self.uc.mem_write(clip + 0xC, b'\x3c')
        self.f32(clip + 0x10, 1)
        self.f32(clip + 0x14, 2 / 60)
        self.put(clip + 0x24, channels + 0x280)
        self.put(clip + 0x28, channels + 0x240)
        self.put(clip + 0x2C, channels + 0x200)
        self.put(channels + 0x200, 0xFFFFFFFF)
        self.uc.mem_write(channels + 0x240, struct.pack('<12h', 0, 100, 0, 0, 200, 140, 300, 1024, 0, 100, 0, 0))
        for field, offset in ((0xC58, 0), (0xC5C, 0x80), (0xC74, 0x40), (0xC78, 0xC0)):
            self.put(who + field, channels + offset)
        for channel in (channels, channels + 0x40, channels + 0x80, channels + 0xC0):
            self.put(channel, clip)
            self.f32(channel + 4, 0)
            self.f32(channel + 8, 1)
            self.put(channel + 0x28, channels + 0x300)
            self.put(channel + 0x2C, channels + 0x340)
        for field in (0xC30, 0xC34):
            self.put(who + field, channels + 0x380)
        self.f32(channels + 0x38C, 1)  # neutral root quaternion
        self.put(who + 0xC1C, 1)
        # Root adjustment transform: identity, no additional yaw/translation.
        self.f32(who + 0xB84, 1)
        self.f32(who + 0xB8C, 1)
        self.f32(who + 0xB94, 1)
        self.f32(who + 0xBA0, 1)
        self.stub_pops.pop(0x31BEB0, None)
        self.stub_pops.pop(0x2D6B70, None)
        self.stub_pops.update({0xDF9B0: 8, 0xDFA50: 0, 0xDFB40: 8})

    def clone(self, old, new, slot):
        raw = bytearray(self.uc.mem_read(old, 0x1000))
        for i in range(0, len(raw), 4):
            value = struct.unpack_from('<I', raw, i)[0]
            if old <= value < old + 0x1000:
                struct.pack_into('<I', raw, i, value + new - old)
        self.uc.mem_write(new, bytes(raw))
        self.uc.mem_write(new + 0x2E, bytes([slot]))
        return new

    def place(self, who, x, z, vx=0, vz=0):
        pos = self.get(who + 0x18)
        self.uc.mem_write(pos + 0x30, struct.pack('<8f', x, 0, z, 1, vx, 0, vz, 0))
        self.f32(pos + 0x50, 0)  # heading is an integer, overwritten below
        heading = 0 if self.direction * (1 if self.get(who + 0x38) == self.KICK_TEAM else -1) > 0 else 0x8000
        for base in (self.get(who + 0x10) + 0xC, self.get(who + 0x10) + 0x10,
                     self.get(who + 0x14) + 0x28, pos + 0x50):
            self.put(base, heading)

    def coverage(self, rows):
        players = [self.KICKER]
        for slot, (x, z, vx, vz) in enumerate(rows, 1):
            who = self.COVERAGE if slot == 1 else self.clone(self.COVERAGE, 0x2020000 + slot * 0x1000, slot)
            self.place(who, x, z, vx, vz)
            players.append(who)
        for who, nxt in zip(players, players[1:] + [0]):
            self.put(who + 0x34, nxt)
        self.put(self.KICK_TEAM + 4, players[0])
        return players[1:]

    def block(self, who, kind=0):
        node = codec.Node(0x11, 6, [kind, 0, 1, 0, 2, 0, 0, 0]).to_bytes()
        decoded = 0x2018000
        self.run(0x2B5D60, ecx=decoded, edx=int.from_bytes(node[4:], 'little'))
        self.uc.mem_write(self.OPS, node)
        for i in range(8):
            self.f32(who + 0x630 + i * 4, self.readf(decoded + i * 12 + 4))
        self.run(0x2400B0, ecx=who)
        return self.get(who + 0x510)

    def selector(self, who, mode=2):
        out = self.CONTACT + 0x100
        self.run(0x2FAFF0, ecx=who, edx=self.get(who + 0x18) + 0x30,
                 args=(self.get(who + 0x114), mode, 0, out, out + 4, out + 8, out + 12))
        result = bytes(self.uc.mem_read(out, 16))
        self.run(self.CALLBACK + 0x70)  # balance the native ST0 return
        return result

    def contact_fixture(self, who, target):
        """Valid idle players and neutral roster inputs; no selector/stance doubles."""
        for team in (self.KICK_TEAM, self.RECEIVE_TEAM):
            self.put(team + 0x404, team + 0x500)
            self.f32(team + 0x504, 1)
        for p in (who, target):
            self.animation(p)
            self.put(p + 0x904, 0x50F4EC)
            self.put(p + 0xE38, self.get(p + 0xE38) | 8)
            self.put(p + 0xF30, self.get(p + 0x38) + 0x400)
        self.put(0xC16BCC, 1)  # one-shot diagnostic already recorded
        self.put(0xE60280, self.RECEIVE_TEAM)
        # Paired clip asset installation and the stats notification are leaves.
        # Contact eligibility, native animation choice, pairing and flags run.
        self.stub_pops.update({0x30E000: 0, 0xA1EC0: 0})

    def _hook(self, uc, address, size, data):
        if address == 0x31B92E:
            # Immediately after the real DF8B0 key lookup. Record the two bone
            # keys and their times, before decompression / final skeletal output.
            sp = uc.reg_read(x86.UC_X86_REG_ESP)
            channel = uc.reg_read(x86.UC_X86_REG_EBX)
            bone_keys = self.get(self.get(channel) + 0x24)
            self.samples.append(((self.get(sp + 0x18) - bone_keys) // 4,
                                 (self.get(sp + 0xC) - bone_keys) // 4,
                                 self.readf(sp + 0x20), self.readf(sp + 0x14),
                                 self.readf(channel + 4)))
        self.trace.append(address)
        super()._hook(uc, address, size, data)


class CardMachine(NativeMachine):
    """Run the actual eleven-circle draw loop through native quad construction."""
    def __init__(self, payload, *, video=0):
        self.video = video
        self.centers, self.quads = [], []
        self.matrix = None
        super().__init__(payload)
        self.stub_pops.update({0x66B20: 0, 0x2CB90: 8, 0x2CA00: 0})

    def _hook(self, uc, address, size, data):
        sp = uc.reg_read(x86.UC_X86_REG_ESP)
        if address == 0x37290:  # device video-mode query only
            uc.reg_write(x86.UC_X86_REG_EAX, self.video)
            self._ret()
            return
        if address == 0x2D2A0:  # GPU begin: the native quad transform is complete
            self.matrix = struct.unpack('<16f', uc.mem_read(self.get(sp + 12), 64))
            self.quads.append([])
            self._ret(12)
            return
        if address == 0x2CB50:  # GPU vertex submission
            x, y, z = struct.unpack('<3f', uc.mem_read(sp + 4, 12))
            a = self.matrix
            self.quads[-1].append(tuple(x * a[j] + y * a[4+j] + z * a[8+j] + a[12+j] for j in range(3)))
            self._ret(12)
            return
        if address == 0x16513E:
            self.centers.append(struct.unpack('<3f', uc.mem_read(sp + 0x20, 12)))
        super()._hook(uc, address, size, data)

    def card(self, *, rectangle=(64, 300, 576, 440), runup=5, mirror=False, play=False):
        from tests.mod_editor.test_nfl2k5_widescreen_polish import RetailExecutionTests as Graphics
        camera, point = 0xBD7030, 0x2019000
        self.uc.mem_write(camera, Graphics().camera(perspective=False, target=(0, 0, 640, 480)))
        self.put(0xA6A9D0, 640); self.put(0xA6A9D4, 480)
        self.put(0xA6AFB4, wide.ACTIVE_CAMERA_VA)
        form = self.KICK_BOOK + 0x200
        self.put(form, point + 0x100)
        self.uc.mem_write(point + 0x100, 'Kickoff\0'.encode('utf-16-le'))
        slots = bytes(self.uc.mem_read(form + alignment.SLOT_BASE, alignment.SLOTS_SIZE))
        self.uc.mem_write(form + alignment.SLOT_BASE,
                          alignment.with_xz(slots, alignment.kickoff_xz_2026(runup)))
        self.uc.mem_write(point, struct.pack('<4f', 0, 0, -75, 1))
        self.put(point + 0x300, -1); self.put(point + 0x304, -1)
        self.run(0x165760)  # retail circle style: radius 15
        self.run(0x144360, args=(point, 0, form, point + 0x400 if play else 0, 0x3F800000))
        # 144BA0 supplies this bounded viewport to 2BB00 after clamping it to
        # its card art. Exercise the same rectangle update and camera activation.
        x0, y0, x1, y1 = rectangle
        self.uc.mem_write(point + 0x10, struct.pack('<8f', x0, y0, 0, 0, x1, y1, 1, 0))
        self.run(0x2BB00, ecx=camera, edx=point + 0x10)
        self.run(0x2AC80, ecx=camera)
        self.run(0x1807F0, args=(point, 1, 1))
        if mirror:
            self.put(0xBDFC10, self.get(0xBDFC10) | 1)
        self.run(0x181010, ecx=point + 0x200, edx=form,
                 args=(0, point + 0x240, 2, camera, point + 0x300, 0x41200000))
        return self.quads


@unittest.skipUnless(RETAIL.is_file() and uni is not None and Cs is not None,
                     PRIVATE_REASON + '; unicorn/capstone required')
class V2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_XBE_SHA256:
            raise unittest.SkipTest('private retail XBE SHA-256 differs')
        cls.base = kr.apply(cls.retail)[0]
        cls.fixed = dk.apply(cls.base)[0]
        from tests.nfl2k5_allocator_stack import REQUESTS
        cls.grown = relocated.apply(space.apply(cls.fixed, REQUESTS, scaleout=True)[0])[0]
        cls.previous = previous_payload(cls.retail)
        prior = json.loads((ROOT / 'docs/nfl2k5_kickoff_fixes_receipts.json').read_text())
        if hashlib.sha256(cls.previous).hexdigest() != prior['legacy_output_sha256']:
            raise AssertionError('previous kickoff receipt does not replay exactly')

    def variants(self):
        return ((self.fixed, dk.FLAGS), (self.grown, relocated._sites(self.grown)[1]['va']))

    def test_reject_previous_xbe_and_mixed_new_hooks_without_mutation(self):
        self.assertEqual(dk.status(self.previous), 'foreign')
        with self.assertRaises(dk.DynamicKickoffError): dk.apply(self.previous)
        for payload, state in self.variants():
            self.assertEqual(dk.status(payload), 'applied')
            self.assertEqual(dk.apply(payload)[0], payload)
            for name in ('root_motion', 'block_target', 'diagram'):
                va, retail = dk.HOOKS[name]
                offset = dk._offset(payload, va, len(retail))
                mixed = bytearray(payload)
                mixed[offset:offset + len(retail)] = retail
                before = bytes(mixed)
                self.assertEqual(dk.status(mixed), 'foreign')
                with self.assertRaises(ValueError): dk.apply(mixed)
                self.assertEqual(bytes(mixed), before)

    def test_committed_xbe_receipts_replay_owner_digest_and_allocator_edits(self):
        receipt = json.loads((ROOT / 'docs/nfl2k5_kickoff_v2_receipts.json').read_text())
        # This is a historical v2 receipt. The current compiler is v3; its own
        # exact receipt replay is covered by test_nfl2k5_kickoff_v3.py.
        legacy_v2 = v2_payload(self.base)
        allocated = space.apply(legacy_v2, receipt['union_requests'], scaleout=True)[0]
        self.assertEqual(hashlib.sha256(allocated).hexdigest(), receipt['union_allocated_sha256'])
        for source, name, digest in ((self.base, 'legacy', 'legacy_output_sha256'),
                                     (allocated, 'relocated', 'relocated_output_sha256')):
            replay = bytearray(source)
            edits = receipt[name]['edits'] + receipt[name + '_section_digest_edits']
            if name == 'relocated': edits += receipt['relocated_allocator_metadata_edits']
            for edit in edits:
                start = edit['offset']; after = bytes.fromhex(edit['after'])
                before = source[start:start + len(after)]
                if 'before' in edit: self.assertEqual(before.hex(), edit['before'])
                else: self.assertEqual(hashlib.sha256(before).hexdigest(), edit['before_sha256'])
                replay[start:start + len(after)] = after
            self.assertEqual(hashlib.sha256(replay).hexdigest(), receipt[digest])
            self.assertEqual(dk.status(bytes(replay)), 'foreign')
            with self.assertRaises(ValueError): dk.apply(bytes(replay))

    def test_prior_sampler_oscillates_and_restore_hides_world_deltas(self):
        m = NativeMachine(self.previous)
        m.launch(); who = m.COVERAGE
        m.animation(who); m.place(who, 123, 456)
        m.put(who + 0x98C, 0x800)  # retail height/root callback path
        m.put(0xE60268, who); m.watch_player = who
        phases, worlds, writes = [], [], []
        for frame in range(8):
            m.root_writes.clear()
            m.run(0x28DFE0); m.run(0x218010, esi=who)
            phases.append(m.samples[-1][0])
            worlds.append(bytes(m.uc.mem_read(who + 0xB30, 48)))
            writes.append(list(m.root_writes))
        self.assertEqual(phases, [1, 0] * 4)
        self.assertEqual(len(set(worlds)), 1)
        self.assertTrue(all(any(pc == 0x2CC5CA for pc, *_ in row) for row in writes))
        self.assertNotEqual(writes[0], writes[1])

    def test_native_fixed_frame_all_19_roles_ready_approach_flight_and_release(self):
        for payload, state in self.variants():
            for direction in (-1, 1):
                for role, slots in (('COVERAGE', range(1, 11)), ('BLOCKER', range(2, 11))):
                    for slot in slots:
                        with self.subTest(state=state, direction=direction, role=role, slot=slot):
                            m = NativeMachine(payload, direction=direction, state_va=state)
                            who = getattr(m, role)
                            m.uc.mem_write(who + 0x2E, bytes([slot]))
                            m.put(who + 0x100, slot % 2 - 1)  # CPU and selected human
                            m.animation(who); m.place(who, 123, 456)
                            m.put(0xE60268, who); m.put(who + 0x98C, 0x800)
                            m.put(dk.PLAY_STATE, 13)
                            m.run(0x218010, esi=who)  # canonical idle entry
                            initial = bytes(m.uc.mem_read(who + 0xB30, 48))
                            m.watch_player = who
                            for stage in ('ready', 'approach', 'flight'):
                                if stage != 'ready': m.put(dk.PLAY_STATE, 14)
                                if stage == 'flight': m.launch()
                                for frame in range(6):
                                    m.run(0x28DFE0)
                                    m.run(dk.HOOKS['plan'][0], ecx=who)
                                    m.run(0x218010, esi=who)
                                    m.run(0x2CC4F0, ecx=who, args=(0x447A0000, 0x447A0000))
                                    self.assertEqual(bytes(m.uc.mem_read(who + 0xB30, 48)), initial)
                                    self.assertEqual(m.samples[-1], (0, 1, 0, struct.unpack('<f', struct.pack('<f', 1/60))[0], 0))
                                    self.assertEqual(m.get(who + 0xC54), 1)
                            self.assertEqual(m.root_writes, [])
                            m.position(0, direction * 3600, m.RETURNER)
                            m.event('touch' if slot % 2 else 'ground')
                            m.run(0x218010, esi=who)
                            self.assertEqual(m.samples[-1][0], 1)
                            self.assertTrue(m.root_writes)
                            m.run(0x2CC4F0, ecx=who, args=(0x447A0000, 0x447A0000))
                            self.assertEqual(m.readf(who + 0xB30), 1000)

    def test_stale_clip_and_blends_stay_fixed_without_reentering_ready(self):
        # Retain the recorded v2 initializer proof and test v5's stronger
        # contract: freeze the selected channels without restarting a stance.
        for payload, state in [(v2_payload(self.base), dk.FLAGS)] + list(self.variants()):
            historical = payload == v2_payload(self.base)
            for direction in (-1, 1):
                m = NativeMachine(payload, direction=direction, state_va=state)
                m.launch(); who = m.BLOCKER
                m.animation(who); m.place(who, 123, 456)
                idle = m.get(m.get(who + 0xC58)); stale = idle + 0x80
                m.uc.mem_write(stale, bytes(m.uc.mem_read(idle, 0x30)))
                for field in (0xC58, 0xC74):
                    m.put(m.get(who + field), stale)
                    m.f32(m.get(who + field) + 4, .02)
                m.put(who + 0xC1C, 7); m.put(who + 0x904, 0x50F4EC)
                m.f32(who + 0x110, 1); m.put(who + 0x118, 2)
                # A real turn updates the descriptor, sampler and transform
                # heading caches together. Keep the stale-clip input valid.
                m.run(0x1A89E0, ecx=who, edx=0x4000)
                self.assertEqual(m.get(who + 0xB50), 0x4000)
                m.run(0x218010, esi=who)
                if historical:
                    self.assertIn(0x2D6B70, m.trace); self.assertIn(0x31BD40, m.trace)
                else:
                    self.assertNotIn(0x2D6B70, m.trace)
                for field in (0xC58, 0xC74):
                    self.assertEqual(m.get(m.get(who + field)), idle if historical else stale)
                    self.assertEqual(m.readf(m.get(who + field) + 4), 0)
                self.assertEqual(m.get(who + 0xC1C) & 6, 0)
                self.assertEqual(m.get(who + 0xB50), 0 if direction < 0 else 0x8000)
                m.watch_player = who
                for frame in range(8): m.run(0x218010, esi=who)
                self.assertEqual(m.root_writes, [])

    def test_native_selector_counterexample_and_lead_confidence_gate(self):
        for direction in (-1, 1):
            for kind in (0, 4):
                m = NativeMachine(self.previous, direction=direction)
                m.launch(); m.place(m.BLOCKER, 0, direction * 3000)
                opponents = m.coverage([(0, direction * 2500, 0, direction * 100),
                                        (0, direction * 2000, 0, direction * 100)])
                m.position(0, direction * 3600, m.RETURNER); m.event('touch')
                block = m.block(m.BLOCKER, kind)
                self.assertEqual(m.get(block + 0x40), opponents[1])
                self.assertEqual(m.readf(block + 0x44), 0)
                for native in (0x239C10, 0x239C40, 0x23A3E0, 0x2FAFF0):
                    self.assertIn(native, m.trace)
                    self.assertNotIn(native, m.stub_pops)
                if kind == 4:
                    m.run(0x23A630, ecx=m.BLOCKER)
                    self.assertEqual(m.get(block + 0x40), 0)

    def test_every_blocker_selects_nearest_and_natively_pairs_on_contact(self):
        for payload, state in self.variants():
            for direction in (-1, 1):
                for carrier in (0, 1):
                    for slot in (s for s in range(11) if s != carrier):
                        with self.subTest(state=state, direction=direction, carrier=carrier, slot=slot):
                            m = NativeMachine(payload, direction=direction, state_va=state)
                            m.launch(); who = m.BLOCKER
                            m.uc.mem_write(who + 0x2E, bytes([slot]))
                            m.uc.mem_write(m.RETURNER + 0x2E, bytes([carrier]))
                            x = -1800 + 400 * (slot % 10)
                            rows = [(-1800 + 400*i, direction * (2000 + 20*i), 0, direction*100) for i in range(10)]
                            opponents = m.coverage(rows)
                            m.place(who, x, direction * 2600)
                            m.position(0, direction * 3600, m.RETURNER); m.event('touch')
                            block = m.block(who)
                            nearest = min(range(10), key=lambda i: (rows[i][0]-x)**2 + (rows[i][1]-direction*2600)**2)
                            target = opponents[nearest]
                            self.assertEqual(m.get(block + 0x40), target)
                            self.assertEqual(m.get(block), 0x23CE70)
                            self.assertEqual((m.get(block + 0xAC) >> 4) & 15, 2)
                            self.assertEqual(m.readf(block + 0x44), 1)
                            self.assertEqual(m.get(who + 0xE38) & 8, 8)
                            m.contact_fixture(who, target)
                            m.run(0x23CE70, ecx=who)
                            self.assertGreater(m.readf(who + 0x110), 0)
                            # Supply the touching pair at the broadphase boundary.
                            # Eligibility, facing checks, contact and pairing run.
                            m.place(target, x, direction * 2550, 0, direction*100)
                            m.uc.reg_write(x86.UC_X86_REG_EAX, target)
                            m.run(0x1DA980, ecx=who)
                            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 1)
                            self.assertEqual(m.get(who + 0x9D0), target)
                            self.assertEqual(m.get(target + 0x9D0), who)
                            for p in (who, target):
                                self.assertEqual(m.get(p + 0xE38) & 0xA, 0xA)
                                m.run(0x231EE0, ecx=m.get(p + 0x10))
                                self.assertNotEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 0)
                            m.run(0x23CE70, ecx=who)
                            self.assertEqual(m.get(who + 0x780) & 8, 8)
                            self.assertIn(0x2336E0, m.trace)
                            self.assertEqual(m.fpu_stubs, {})

    def test_target_filters_zero_velocity_refresh_and_bounded_cycle(self):
        for payload, state in self.variants():
            for direction in (-1, 1):
                m = NativeMachine(payload, direction=direction, state_va=state)
                m.launch(); who = m.BLOCKER
                m.place(who, 0, direction*3000)
                rows = [(1000, 2000, 0, 100), (0, 2800, 0, 100), (0, 2990, 0, -100),
                        (0, 3100, 0, -100), (0, 2995, 0, 0), (float('nan'), 2999, 0, 0),
                        (0, 2998, 0, float('nan')), (80, 2850, -100, 100), (0, 2920, 0, 0)]
                opponents = m.coverage([(x, direction*z, vx, direction*vz) for x,z,vx,vz in rows])
                m.put(opponents[4] + 0x48, 1)
                m.place(m.KICKER, 0, direction*2999)  # closest, excluded slot zero
                m.position(0, direction*3600, m.RETURNER); m.event('touch')
                block = m.block(who)
                self.assertEqual(m.get(block + 0x40), opponents[8])  # stationary release frame
                m.place(opponents[8], 0, direction*2800)
                m.place(opponents[1], 0, direction*2880, 0, direction*100)
                m.run(0x23CD60, ecx=who)
                self.assertEqual(m.get(block + 0x40), opponents[1])  # 80 cm closer, within retail hysteresis
                self.assertEqual(m.get(block + 0x48), 0)
                m.put(opponents[-1] + 0x34, opponents[0])  # corrupted list cannot loop forever
                self.assertEqual(struct.unpack('<I', m.selector(who)[:4])[0], opponents[1])
                for p in opponents: m.put(p + 0x48, 1)
                self.assertEqual(struct.unpack('<I', m.selector(who)[:4])[0], 0)
                self.assertEqual(m.get(block + 0x40), 0)

    def test_target_guard_replays_retail_outside_released_return_blockers(self):
        for payload, state in self.variants():
            for case in ('safety', 'scrimmage', 'onside', 'ready', 'before_touch', 'carrier', 'kicker', 'hidden', 'slot11', 'lead'):
                outputs = []
                for source in (self.base, payload):
                    m = NativeMachine(source, state_va=state, onside=case == 'onside')
                    m.launch(); m.place(m.BLOCKER, 0, 3000)
                    m.coverage([(0, 2500, 0, 100), (0, 2000, 0, 100)])
                    if case != 'before_touch':
                        m.position(0, 3600, m.RETURNER); m.event('touch')
                    who = m.BLOCKER
                    if case == 'safety': m.put(dk.PHASE, 1)
                    if case == 'scrimmage': m.put(dk.PHASE, 4)
                    if case == 'ready': m.put(dk.PLAY_STATE, 13)
                    if case == 'carrier': m.put(m.BALL, who)
                    if case == 'kicker': who = m.KICKER
                    if case == 'hidden': m.put(who + 0x48, 1)
                    if case == 'slot11': m.uc.mem_write(who + 0x2E, b'\x0b')
                    m.block(who, 4 if case == 'lead' else 0)
                    outputs.append(m.selector(who, 3 if case == 'lead' else 2))
                self.assertEqual(*outputs, case)

    def test_all_eleven_native_circle_quads_fit_cards_four_three_and_widescreen_v3(self):
        rectangles = ((64, 300, 576, 440), (64, 300, 240, 440), (240, 300, 416, 440), (416, 300, 592, 440))
        for payload, state in self.variants():
            widened, receipt = wide.apply(payload)
            self.assertEqual(receipt['version'], 3)
            for rectangle in rectangles:
                for runup, video, mirror, play in ((1, 0, False, False), (5, 2, True, False), (15, 0, False, True)):
                    results = []
                    for source in (payload, widened):
                        m = CardMachine(source, video=video)
                        quads = m.card(rectangle=rectangle, runup=runup, mirror=mirror, play=play)
                        self.assertEqual(len(quads), 11)
                        self.assertTrue(all(len(q) == 4 for q in quads))
                        x0, y0, x1, y1 = rectangle
                        for slot, quad in enumerate(quads):
                            for x, y, z in quad:
                                self.assertTrue(x0 < x < x1 and y0 < y < y1 and z > 0,
                                                (state, rectangle, runup, video, mirror, play, slot, x, y, z))
                        results.append(quads)
                    self.assertEqual(*results)
        m = CardMachine(self.previous)
        quads = m.card()
        self.assertTrue(all(y > 300 for x, y, z in quads[0]))
        self.assertTrue(all(min(y for x, y, z in q) < 300 for q in quads[1:]))

    def test_other_private_formations_have_byte_identical_diagram_coordinates(self):
        archive_path = RETAIL.parent / 'vc_53450030'
        if not archive_path.is_dir(): self.skipTest('private extracted PLAY archive required')
        forms = {}
        total = 0
        with alignment.recode.OuterImage(archive_path) as archive:
            for book, refs in alignment._load(archive):
                parsed = alignment.parse_playbook_resource(archive.read_entry(book.entry_index))
                for f in parsed.formations:
                    start = alignment.FORMATION_BASE + f.index * alignment.FORMATION_SIZE
                    raw = book.body[start:start + alignment.FORMATION_SIZE]
                    forms[(f.name, raw[4:])] = raw
                    total += 1
        self.assertGreater(total, 1000)
        # All retail formations, including retail type 8, plus the newly aligned
        # type 9. Only the dynamic type-8 row is meant to change.
        return_form = bytearray(next(raw for (name, _), raw in forms.items() if name == 'Kick Return'))
        return_form[alignment.SLOT_BASE:] = alignment.with_xz(return_form[alignment.SLOT_BASE:], alignment.KICK_RETURN_XZ_2026)
        forms[('Kick Return', bytes(return_form[4:]))] = bytes(return_form)
        for payload, state in self.variants():
            machines = [NativeMachine(self.base), NativeMachine(payload, state_va=state)]
            for (name, _), raw in forms.items():
                result = []
                for m in machines:
                    form, point = m.KICK_BOOK + 0x200, m.CONTACT
                    m.uc.mem_write(form, raw); m.put(form, m.CONTACT + 0x300)
                    m.uc.mem_write(m.CONTACT + 0x300, (name+'\0').encode('utf-16-le'))
                    m.put(0xBDFC20, form); m.put(0xBDFBE4, 1)
                    points = []
                    for slot in range(11):
                        base = alignment.SLOT_BASE + slot*14
                        x = struct.unpack_from('<h', raw, base + 2)[0]
                        z = struct.unpack_from('<h', raw, base + 8)[0]
                        m.uc.mem_write(point, struct.pack('<4f', x, 0, z, 1))
                        m.run(0x180120, args=(point, 1))
                        points.append(bytes(m.uc.mem_read(point, 16)))
                    m.trace.clear()
                    result.append(points)
                self.assertEqual(*result, name)

    def test_dynamic_diagram_does_not_change_world_or_lateral_only_pass(self):
        for payload, state in self.variants():
            for mode, depth in ((0, 1), (1, 0)):
                outputs = []
                for source in (self.base, payload):
                    m = NativeMachine(source, state_va=state)
                    form = m.KICK_BOOK + 0x200
                    m.put(form, m.CONTACT + 0x300)
                    m.uc.mem_write(m.CONTACT + 0x300, 'Kickoff\0'.encode('utf-16-le'))
                    m.put(0xBDFC20, form); m.put(0xBDFBE4, mode)
                    result = []
                    for x, z in alignment.kickoff_xz_2026():
                        m.uc.mem_write(m.CONTACT, struct.pack('<4f', x, 0, z, 1))
                        m.run(0x180120, args=(m.CONTACT, depth))
                        result.append(bytes(m.uc.mem_read(m.CONTACT, 16)))
                    outputs.append(result)
                self.assertEqual(*outputs)


if __name__ == '__main__':
    unittest.main()
