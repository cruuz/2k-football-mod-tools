"""Bounded native kickoff replays. Run standalone; --record writes v5 only.

The executable is private. Synthetic skeletons and decoded input are explicit
boundaries; no disc, archive, game process, display or audio device is opened.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import math
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_nfl2k5_dynamic_kickoff import RETAIL, PRIVATE_REASON, uni, x86, Cs
from tests.mod_editor.test_nfl2k5_kickoff_v2 import NativeMachine, v2_payload, previous_payload
from tests.mod_editor.test_nfl2k5_kickoff_v3 import patch_evidence, replay_edits, v3_payload, digest, HELD
from tests.nfl2k5_kickoff_frame import PreKickMachine, FrameMachine, WriteReceipt, PHASES
from mod_editor.core import nfl2k5_dynamic_kickoff as dk
from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
from mod_editor.core import nfl2k5_play_codec as codec, nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import RETAIL_XBE_SHA256, _sections, section_digest

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / 'docs/nfl2k5_kickoff_v5_receipts.json'
NATIVE_READY = (0x186240, 0x185B50, 0x185070, 0x1AE490, 0x1CD550,
                0x2388D0, 0x238660, 0x2132A0, 0x2FCAC0, 0x200D00,
                0x1FFFE0, 0x218150, 0x31B910)


def v4_payload(base):
    return replay_edits(base, json.loads((ROOT / 'docs/nfl2k5_kickoff_v4_receipts.json').read_text()), 'legacy')


def historical_payloads(retail, base):
    """Reconstruct all eight old executables against their published SHA-256s."""
    v2_receipt = json.loads((ROOT / 'docs/nfl2k5_kickoff_v2_receipts.json').read_text())
    for version in range(1, 5):
        filename = 'nfl2k5_kickoff_fixes_receipts.json' if version == 1 else f'nfl2k5_kickoff_v{version}_receipts.json'
        receipt = json.loads((ROOT / 'docs' / filename).read_text())
        old = previous_payload(retail) if version == 1 else replay_edits(base, receipt, 'legacy')
        assert hashlib.sha256(old).hexdigest() == receipt['legacy_output_sha256']
        yield f'v{version}_legacy', old
        # v1 predates the union field. v2 recorded the same union; the exact
        # v1 allocated-image hash below proves that reconstruction, too.
        requests = receipt.get('union_requests', v2_receipt['union_requests'])
        allocated = space.apply(old, tuple(tuple(row) for row in requests), scaleout=True)[0]
        assert hashlib.sha256(allocated).hexdigest() == receipt['union_allocated_sha256']
        if version == 1:
            code, _ = relocated._sites(allocated)
            edit = next(e for e in receipt['relocated']['edits'] if e['offset'] == code['raw'])
            grown = bytearray(space.install_code(allocated, relocated.OWNER, bytes.fromhex(edit['after']))[0])
            for edit in receipt['relocated']['edits']:
                raw = bytes.fromhex(edit['after']); offset = edit['offset']
                before = allocated[offset:offset + len(raw)]
                # V1 records short hook inputs as exact bytes and its cave
                # input as a digest. Preserve both historical preconditions.
                if 'before' in edit:
                    assert before.hex() == edit['before']
                else:
                    assert hashlib.sha256(before).hexdigest() == edit['before_sha256']
                grown[offset:offset + len(raw)] = raw
            for section in _sections(grown):
                grown[section.header_offset + 36:section.header_offset + 56] = section_digest(grown, section)
            grown = bytes(grown)
            assert hashlib.sha256(grown).hexdigest() == receipt['relocated_output_sha256']
        else:
            grown = replay_edits(allocated, receipt, 'relocated')
        yield f'v{version}_grown', grown


class NativeSetupMachine(PreKickMachine):
    """Both formation tasks, actual game locomotion callback and ready assets.

    1DEFA0 installs callback 2388D0 and private table storage. The previous
    fixture's RET callback hid its forced ready transition. Animation +30 is
    the cosine cache, not a second pose pointer; +34 is the shared pose array.
    The bounded synthetic skeleton remains an explicit asset boundary.
    """
    instruction_limit = 5_000_000

    def _skeletons(self):
        super()._skeletons()
        # 90570 normally loads these mesh adjustment axes and bone indices.
        # 91890 -> 901E0 -> 1C2530 normalizes the axis; a zero-filled record
        # creates NaNs in 2177A0's foot query. Supply valid synthetic records
        # alongside the synthetic skeleton, retaining all native adjustment math.
        for slot, source, target in ((1, 1, 2), (2, 5, 6)):
            record = 0xB65B80 + slot * 0x20
            self.uc.mem_write(record, struct.pack('<4f2I', 0, 1, 0, 0, source, target))

    def __init__(self, payload, **kwargs):
        self.setup_frame, self.foot_trace = -1, []
        super().__init__(payload, **kwargs)
        self.setup_callbacks = {}
        self.run(0x48BE0, ecx=0xE5FCA0, edx=20260907)  # native pose RNG constructor
        self.put(0xE3C014, 0x205F800)  # native spare table swapped by 2388D0
        for pc in NATIVE_READY:
            self.uc.hook_add(uni.UC_HOOK_CODE, self._hook, begin=pc, end=pc)
        self.uc.hook_add(uni.UC_HOOK_CODE, self._hook, begin=0x2002EB, end=0x2002EB)
        for index, who in enumerate(self.players):
            base = 0x2100000 + index * 0x8000
            self.put(who + 0x940, 0x2388D0)
            self.put(who + 0x93C, base + 0x3F00)
            self.run(0x2CC470, ecx=self.get(who + 0xC28), args=(who + 0xC2C, who + 0xC30))
            node, operands = base + 0x3E00, base + 0x3E20
            start = bytes.fromhex('0100000001044080' if index == 0 else '0100000001034080')
            terminal = codec.Node(0x11, 6, [0, 0, 1, 0, 2, 0, 0, 0]).to_bytes()
            self.put(who + 0x61C, node)
            self.put(node, 2); self.put(node + 4, operands)
            self.uc.mem_write(operands, start + terminal)
            self.run(0x2B5D60, ecx=0x2018000, edx=int.from_bytes(start[4:], 'little'))
            for n in range(4):
                self.f32(who + 0x630 + n * 4, self.readf(0x2018004 + n * 12))
            try:
                self.run(0x186240, ecx=who)  # initializer chooses 185070 or 1853D0
            except Exception as exc:
                raise AssertionError(f'setup player {index}, PC {self.uc.reg_read(x86.UC_X86_REG_EIP):#x}') from exc
            self.setup_callbacks[who] = self.get(self.get(who + 0x510))
            self.run(0x1CD550, ecx=who, edx=0x50F1E4, budget=300_000)
        self.visited.clear(); self.writes.clear()
        self.foot_trace.clear()

    def _hook(self, uc, address, size, data):
        if address == 0x2002EB:
            # Immediately after 1FFFE0's native 218150 bone-12 sample returns.
            # ESI retains the player; locals +14 and +30 hold sample time and
            # the output vector. Observe only: no sampler or pose is replaced.
            who, stack = uc.reg_read(x86.UC_X86_REG_ESI), uc.reg_read(x86.UC_X86_REG_ESP)
            raw = bytes(uc.mem_read(stack + 0x30, 16))
            assert all(math.isfinite(value) for value in struct.unpack('<4f', raw)), 'invalid foot sample'
            self.foot_trace.append([self.setup_frame, self.players.index(who), self.phase,
                                    self.get(stack + 0x14),
                                    raw.hex()])
        super()._hook(uc, address, size, data)

    def snapshot(self):
        result = super().snapshot()
        # Native clip installation swaps the channel pointers. Preserve the
        # physical-bank write watches and also read the active channels, so
        # an alternating bank cannot hide a changed clip/time/rate.
        for index, who in enumerate(self.players):
            for name, offset in (('active_primary', 0xC58), ('active_secondary', 0xC74)):
                result[index, name] = bytes(self.uc.mem_read(self.get(who + offset), 12))
        return result

    def complete_lineup(self, players):
        self.phase = 0; self.writes.clear()
        for who in players:
            task = self.get(who + 0x510)
            self.put(task + 0x38, 3); self.put(task + 0x3C, 1)
            assert self.get(who + 0x5E4) == 12
            self.run(self.setup_callbacks[who], ecx=who)
            assert self.get(who + 0x5E4) == 13
            self.run(0x1AE490, ecx=who)  # real Start opcode and event wait task
            self.put(who + 0x200, 1)  # scheduler task-group input
        return self.snapshot()


def setup_replay(test, payload, state, direction, historical=False):
    m = NativeSetupMachine(payload, state_va=state, direction=direction)
    trace = WriteReceipt()
    m.complete_lineup(m.held)
    rows, restarts, free_changes = [], Counter(), Counter()
    # Record both entry frames: the second copies the first sample's height
    # into the previous-transform cache. Neither is omitted from the receipt.
    previous = None
    baseline = None
    def held_pose(snapshot):
        # Native matrix products can change the sign of IEEE zero. Preserve
        # those exact bits in the trace, but do not call that physical motion.
        return {k: (b''.join(b'\0\0\0\0' if raw[n:n+4] == b'\0\0\0\x80' else raw[n:n+4]
                            for n in range(0, len(raw), 4)) if k[1].startswith('skeleton') else raw)
                for k, raw in snapshot.items() if k[0] in HELD}
    for frame in range(25):
        m.setup_frame = frame
        if frame == 8:
            m.complete_lineup(m.free)
        if frame == 14:
            m.approach()
        if frame == 20:
            # Deliver decoded normal Ball Action at the launch callback ABI.
            # Formation and Start tasks above have already run natively.
            m.put(m.KICKER + 0x61C, m.NODE); m.put(m.NODE + 4, m.OPS)
            m.uc.mem_write(m.OPS, b'\x08'); m.f32(m.KICKER + 0x630, 0)
            m.put(m.CTX + 0x1C4, m.KICKER)
            m.launch()
            test.assertEqual(m.flags() & 15, dk.ACTIVE)
        if frame == 24:
            m.position(0, direction * 3600, m.RETURNER)
            m.event('ground' if direction < 0 else 'touch')
        calls = m.visited.copy()
        current = m.frame(); trace.add(m, current)
        delta = Counter(kind for (p, kind), raw in current.items()
                        if p in HELD and previous is not None and raw != previous[p, kind])
        rows.append(dict(frame=frame, state=m.get(dk.PLAY_STATE), flags=m.flags(), changes=dict(delta),
                         restarts=m.visited[0x1CD550] - calls[0x1CD550],
                         foot_samples=m.visited[0x218150] - calls[0x218150]))
        restarts.update({str(pc): m.visited[pc] - calls[pc] for pc in NATIVE_READY})
        if frame == 1:
            baseline = held_pose(current)
        if 2 <= frame < 24 and not historical:
            test.assertEqual(held_pose(current), baseline,
                             f'native ready frame {frame}: {dict(delta)}')
        test.assertEqual(m.get(dk.PLAY_STATE), 12 if frame < 8 else 13 if frame < 14 else 14)
        test.assertEqual(m.flags() & 7, dk.LANDING if frame == 24 else 0)
        if frame == 24:
            moved = [p for p in HELD if current[p, 'transform'] != previous[p, 'transform']]
            test.assertEqual(moved, list(HELD))
            for who in m.held:
                test.assertGreater(m.readf(m.get(who + 0xC58) + 4), 0)
        if previous is not None:
            for p in (0, 11, 12):
                free_changes[p] += any(raw != previous[player, kind]
                                       for (player, kind), raw in current.items() if player == p)
        previous = current
    return dict(direction=direction, historical=historical, pose_rng_seed=20260907, frames=rows,
                setup_callbacks=[hex(m.setup_callbacks[w]) for w in m.players],
                free_changed_frames=dict(free_changes), contact_moved_players=moved,
                native_calls=dict(restarts), state_writes=m.state_writes,
                foot_trace_columns=['frame', 'player', 'phase_pc', 'sample_time_u32', 'result_xyzw_hex'],
                foot_writer_call_pc='0x2002e6', foot_writer_return_pc='0x2002eb', foot_trace=m.foot_trace,
                trace=trace.result(), trace_sha256=trace.digest())


class ReturnMachine(FrameMachine):
    """Continuous return with native drive tasks, steering, root and collisions.

    Coverage intent and the carrier's straight return are decoded inputs.
    Blocker intent, target refresh, pursuit and collision contacts are native.
    A three-key synthetic run supplies 15 cm/frame at full speed, with a real
    separate stationary band and a 180 degree/second turning-rate input.
    No player is teleported to a target or supplied as a touching pair.
    """
    # Unicorn's instruction counter serializes every instruction. A hard wall
    # timeout bounds this long replay without that overhead; the exact native
    # exit, stack balance and all 27 phases are still required on every frame.
    instruction_limit = 0
    frame_timeout_us = 2_000_000

    def __init__(self, payload, *, carrier_slot=0, **kwargs):
        if carrier_slot not in (0, 1):
            raise ValueError('carrier_slot must identify one of the two deep returners')
        self.carrier_index, self.alternate_index = 11 + carrier_slot, 12 - carrier_slot
        self.decisions, self.pursuits = [], []
        self.waits, self.lane_checks = [], []
        self.return_frame = -1
        super().__init__(payload, radius=45, **kwargs)
        self.RETURNER = self.players[self.carrier_index]
        # Return evidence records every player's final frame state, target and
        # native pursuit/contact. Full pose-write streams belong to setup_replay.
        self.uc.hook_del(self.frame_write_hook)
        self.wait_pc = None
        if dk.status(payload) == 'applied':
            code_va = dk.CAVE_VA if self.state_va == dk.FLAGS else relocated._sites(payload)[0]['va']
            _, labels = dk._code(dk._settings(), cave_va=code_va,
                storage_ranges=((self.state_va, 7),
                                (dk.TB_YARD if self.state_va == dk.FLAGS else self.state_va + 7, 3)))
            self.wait_pc = labels['block_wait']
            self.uc.hook_add(uni.UC_HOOK_CODE, self._hook, begin=self.wait_pc, end=self.wait_pc)
        self.f32(self.SCALAR + 4, 32768)
        self.uc.mem_write(self.CALLBACK + 0xA0, b'\xd9\x05' + struct.pack('<I', self.SCALAR + 4) + b'\xc2\x08\x00')
        for pc in (0x23CE76, 0x23BE60, 0x1DA980):
            self.uc.hook_add(uni.UC_HOOK_CODE, self._hook, begin=pc, end=pc)
        # Paired clip loading and a stats notification are asset/service leaves,
        # as in v2. The native broadphase, eligibility, contact and pair writes run.
        for pc in (0x30E000, 0xA1EC0):
            self.stub_pops[pc] = 0
            self.uc.hook_add(uni.UC_HOOK_CODE, self._hook, begin=pc, end=pc)
        for team, book in ((self.KICK_TEAM, self.KICK_BOOK), (self.RECEIVE_TEAM, self.RECEIVE_BOOK)):
            self.put(team + 0x404, team + 0x500); self.f32(team + 0x504, 1)
            self.put(team + 0x30C, book + 0x400)
        for index, who in enumerate(self.players):
            base = 0x2100000 + index * 0x8000
            run, idle, group = base + 0x100, base + 0x1C00, base + 0x3F00
            self.put(who + 0x40, base + 0x3F80)  # native 158B68 out-of-bounds flag object
            self.put(who + 0xE38, self.get(who + 0xE38) | 8)
            self.uc.mem_write(base + 0x400, struct.pack('<12h',
                              0, 800, 0, 0, 0, 800, 120, 0, 0, 800, 240, 0))
            self.uc.mem_write(idle, bytes(self.uc.mem_read(run, 0x30)))
            self.put(idle + 0x28, base + 0x1D00)
            self.uc.mem_write(base + 0x1D00, struct.pack('<12h', *([0, 800, 0, 0] * 3)))
            self.f32(who + 0xDA8, .05); self.put(who + 0xDAC, group)
            self.f32(who + 0xDB0, .04); self.f32(who + 0xDB4, 1)
            self.put(who + 0xDB8, group + 0x28)
            for n, clip in enumerate((idle, run)):
                address = group + n * 0x28
                self.uc.mem_write(address, struct.pack('<10I', n, clip, 0xFFFF8000, 0x8000,
                    0, 0x3F800000, 0x3F800000, 0, self.CALLBACK + 0x50, self.CALLBACK + 0xA0))
            self.put(who + 0x914, 0)  # select the band from decoded speed
            self.run(0x305920, ecx=who, edx=who + 0xDA0)
            self.run(0x2CC470, ecx=self.get(who + 0xC28), args=(who + 0xC2C, who + 0xC30))
            self.f32(who + 0xB7C, 100); self.f32(who + 0xB80, 20)
        # The non-carrier deep man also owns a native drive block task.
        who = self.players[self.alternate_index]
        self.NODE = 0x2103E00 + self.alternate_index * 0x8000; self.OPS = self.NODE + 0x20
        self.put(who + 0x61C, self.NODE); self.put(self.NODE + 4, self.OPS)
        self.block(who); self.put(who + 0x200, 1)
        self.put(dk.PLAY_STATE, 14)
        self.launch()
        self.position(self.readf(self.RETURNER + 0xB30), self.readf(self.RETURNER + 0xB38), self.RETURNER)
        self.event('touch')
        assert self.flags() & 7 == dk.LANDING
        self.put(dk.POSSESSION, self.RECEIVE_TEAM)
        # The supplied catch attaches the ball's position query to its carrier.
        # Native root integration then moves both with no Python frame writes.
        # Hand/socket animation and a separate ball flight are outside this replay.
        self.put(self.BALL + 0x14, self.RETURNER + 0xB30)

    def _hook(self, uc, address, size, data):
        if address == getattr(self, 'wait_pc', None):
            who = uc.reg_read(x86.UC_X86_REG_EDI)
            self.waits.append([self.return_frame, self.players.index(who)])
        if address == 0x1E0280 and hasattr(self, 'players'):
            for index in (*range(11), self.carrier_index):
                who = self.players[index]
                # External decoded intent before the native whole-team loop:
                # coverage follows its lane; carrier returns straight.
                self.f32(who + 0x110, 0 if index == 0 else 1)
                self.put(who + 0x114, (0 if self.direction > 0 else 0x8000)
                         if index < 11 else (0x8000 if self.direction > 0 else 0))
        if address == 0x23CE76:
            who = uc.reg_read(x86.UC_X86_REG_ECX)
            if who in self.players:
                task = self.get(who + 0x510)
                target = self.get(task + 0x40)
                self.decisions.append([self.return_frame, self.players.index(who),
                                       self.players.index(target) if target in self.players else -1])
        if address == 0x23BE60:
            stack = uc.reg_read(x86.UC_X86_REG_ESP)
            who, target = self.get(stack + 4), self.get(stack + 8)
            if who in self.players and target in self.players:
                self.pursuits.append([self.return_frame, self.players.index(who), self.players.index(target)])
                origin_x, origin_z = self.readf(who + 0xB30), self.readf(who + 0xB38)
                candidates = []
                for index, opponent in enumerate(self.players[1:11], 1):
                    dx = self.readf(opponent + 0xB30) - origin_x
                    dz = self.readf(opponent + 0xB38) - origin_z
                    dot = dx * self.readf(opponent + 0xB40) + dz * self.readf(opponent + 0xB48)
                    if not self.get(opponent + 0x48) and self.direction * dz <= 0 and dot <= 0:
                        candidates.append((4 * dx * dx + dz * dz, index))
                expected = min(candidates)[1] if candidates else -1
                self.lane_checks.append([self.return_frame, self.players.index(who),
                                         self.players.index(target), expected])
        super()._hook(uc, address, size, data)


def return_replay(test, payload, state, direction, carrier_slot=0):
    m = ReturnMachine(payload, state_va=state, direction=direction, carrier_slot=carrier_slot)
    roles = [p for p in range(11, 22) if p != m.carrier_index]
    contacts, passes, kicker_passes = {p: set() for p in roles}, Counter(), Counter()
    rows, previous, pursuing = [], None, {}
    minimum = {p: float('inf') for p in roles}
    for frame in range(900):
        m.return_frame = frame
        start = len(m.pursuits)
        m.frame()
        for _, p, target in m.pursuits[start:]:
            pursuing[p] = target
        for wait_frame, p in m.waits:
            if wait_frame == frame: pursuing[p] = -1
        current = []
        for index, who in enumerate(m.players):
            x, z = m.readf(who + 0xB30), m.readf(who + 0xB38)
            test.assertTrue(math.isfinite(x) and math.isfinite(z))
            target = m.get(m.get(who + 0x510) + 0x40)
            pair = m.get(who + 0x9D0) if m.get(who + 0xE38) & 2 else 0
            peer = m.players.index(pair) if pair in m.players else -1
            current.append([x, z, m.get(who + 0xB50), m.readf(who + 0x110),
                            m.players.index(target) if target in m.players else -1,
                            peer, m.get(who + 0x904), m.get(m.get(who + 0x510))])
        for p in roles:
            if current[p][5] >= 0:
                contacts[p].add(current[p][5])
            for opponent in range(1, 11):
                dx, dz = current[opponent][0] - current[p][0], current[opponent][1] - current[p][1]
                minimum[p] = min(minimum[p], math.hypot(dx, dz))
                if previous is not None:
                    before = direction * (previous[p][1] - previous[opponent][1])
                    after = direction * (current[p][1] - current[opponent][1])
                    progress = direction * (previous[p][1] - current[p][1])
                    # A three-yard corridor measures a passed local opponent;
                    # distinguish a missed contact from pursuit of the kicker.
                    if before >= 0 > after and abs(dx) <= 3 * 91.44 and progress > .01:
                        if current[p][5] != opponent and current[opponent][5] < 0:
                            passes[p] += 1
                            kicker_passes[p] += pursuing.get(p) == 0
        rows.append(current)
        previous = current
        if direction * current[m.carrier_index][1] <= -50 * 91.44:
            break
    else:
        test.fail('carrier did not reach the far goal line within fifteen seconds')
    metrics = {}
    for p in roles:
        choices = [target for _, who, target in m.pursuits if who == p]
        metrics[str(p)] = dict(receiving_slot=p - 11,
            role='alternate_returner' if p == m.alternate_index else 'setup',
            pursuit_calls=len(choices), kicker_pursuits=choices.count(0),
            coverage_targets=sorted(set(choices) - {0}),
            contact_peers=sorted(contacts[p]), waiting_ticks=sum(who == p for _, who in m.waits),
            lane_mismatches=sum(target != expected for _, who, target, expected in m.lane_checks if who == p),
            unblocked_passes=passes[p], passes_while_chasing_kicker=kicker_passes[p],
            closest_coverage_cm=round(minimum[p], 4))
    return dict(direction=direction, carrier_index=m.carrier_index, frames=len(rows), dt='1/60',
                terminal='carrier crosses the far goal line; scoring/officials are outside this fixture',
                input_boundary='coverage follows its lane at 900 cm/s; carrier returns straight; kicker stays',
                ball_boundary='supplied catch at carrier root; ball position query aliases that native moving root',
                frame_columns=['x_cm', 'z_cm', 'heading', 'throttle', 'task_target', 'pair_peer',
                               'descriptor_va', 'task_callback_va'],
                states=rows, decisions=m.decisions, pursuits=m.pursuits, waits=m.waits,
                lane_checks=m.lane_checks,
                metrics=metrics, phase_calls={hex(pc): m.visited[pc] for pc in PHASES})


@unittest.skipUnless(RETAIL.is_file() and uni is not None and Cs is not None,
                     PRIVATE_REASON + '; unicorn/capstone required')
class V5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_XBE_SHA256:
            raise unittest.SkipTest('private retail XBE SHA-256 differs')
        (cls.base, cls.legacy, cls.allocated, cls.grown), cls.evidence = patch_evidence(cls.retail)
        cls.v4 = v4_payload(cls.base)

    def variants(self):
        return [('legacy', self.legacy, dk.FLAGS),
                ('grown', self.grown, relocated._sites(self.grown)[1]['va'])]

    def test_native_both_team_setup_and_receiving_writer_counterexample(self):
        saved = json.loads(RECEIPT.read_text())
        for name, payload, state in [('v4', self.v4, dk.FLAGS)] + self.variants():
            for direction in (-1, 1):
                case = setup_replay(self, payload, state, direction, historical=name == 'v4')
                self.assertEqual(digest(case), digest(saved['setup'][f'{name}_{direction:+d}']))

    def test_exact_replay_identity_foreign_versions_and_all_pins(self):
        saved = json.loads(RECEIPT.read_text())
        self.assertEqual(digest(self.evidence), digest(saved['executable']))
        for source, out, name in ((self.base, self.legacy, 'legacy'),
                                  (self.allocated, self.grown, 'relocated')):
            self.assertEqual(replay_edits(source, self.evidence, name), out)
            for module in (dk, relocated):
                if module is relocated and name == 'legacy':
                    continue
                self.assertEqual(module.status(out), 'applied')
                self.assertEqual(module.apply(out)[0], out)
            for section in _sections(out):
                self.assertEqual(section.stored_digest, section_digest(out, section))
            for va, pin in dk.HOOKS.values():
                off = dk._offset(out, va, len(pin))
                for replacement in (pin, b'\xcc' * len(pin)):
                    mixed = bytearray(out); mixed[off:off + len(pin)] = replacement
                    before = bytes(mixed)
                    for module in (dk, relocated):
                        self.assertEqual(module.status(before), 'foreign')
                        with self.assertRaises(ValueError): module.apply(before)
                    self.assertEqual(bytes(mixed), before)
        for name, old in historical_payloads(self.retail, self.base):
            for module in (dk, relocated):
                self.assertEqual(module.status(old), 'foreign', name)
                with self.assertRaises(ValueError): module.apply(old)

    def test_continuous_return_all_roles_and_both_placements(self):
        saved = json.loads(RECEIPT.read_text())
        for name, payload, state in [('v4', self.v4, dk.FLAGS)] + self.variants():
            for direction in (-1, 1):
                for carrier_slot in (0, 1):
                    key = f'{name}_{direction:+d}_kr{carrier_slot + 1}'
                    case = return_replay(self, payload, state, direction, carrier_slot)
                    self.assertEqual(digest(case), digest(saved['returns'][key]), key)
                    if name != 'v4':
                        for role in case['metrics'].values():
                            self.assertEqual(role['kicker_pursuits'], 0, key)
                            self.assertEqual(role['passes_while_chasing_kicker'], 0, key)
                            self.assertEqual(role['lane_mismatches'], 0, key)
                            self.assertNotIn(0, role['contact_peers'], key)
                    else:
                        self.assertGreater(sum(r['kicker_pursuits'] for r in case['metrics'].values()), 0)
                    for count in case['phase_calls'].values(): self.assertEqual(count, case['frames'])

    def test_lane_preference_waiting_task_and_new_arrival_resume(self):
        for _, payload, state in self.variants():
            for direction in (-1, 1):
                m = NativeMachine(payload, state_va=state, direction=direction)
                m.launch(); who = m.BLOCKER
                m.place(who, 0, direction * 3000)
                opponents = m.coverage([(0, direction * 2400, 0, direction * 100),
                                        (350, direction * 2920, 0, direction * 100)])
                m.position(0, direction * 3600, m.RETURNER); m.event('touch')
                task = m.block(who)
                # The closer Euclidean opponent is off the lane. The arrival
                # in front wins the specified 4*dx^2 + dz^2 comparison.
                self.assertEqual(m.get(task + 0x40), opponents[0])
                for p in opponents: m.put(p + 0x48, 1)
                m.f32(who + 0x110, 1)
                registers = ((x86.UC_X86_REG_EBX, 0xABC123),
                             (x86.UC_X86_REG_EDI, 0xFED321),
                             (x86.UC_X86_REG_EBP, 0x124816))
                for reg, value in registers: m.uc.reg_write(reg, value)
                m.run(0x23CE70, ecx=who, esi=0x192837)
                self.assertEqual(m.get(who + 0x510), task)
                self.assertEqual(m.get(task), 0x23CE70)
                self.assertEqual(m.get(task + 0x40), 0)
                self.assertEqual(m.readf(who + 0x110), 0)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 0)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK + 4)
                for reg, value in registers: self.assertEqual(m.uc.reg_read(reg), value)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESI), 0x192837)
                m.put(opponents[0] + 0x48, 0)
                m.contact_fixture(who, opponents[0])
                m.run(0x23CE70, ecx=who)
                self.assertEqual(m.get(task + 0x40), opponents[0])
                self.assertGreater(m.readf(who + 0x110), 0)
                self.assertEqual(m.get(task), 0x23CE70)

    def test_drive_tick_replays_native_prologue_outside_its_scope(self):
        for _, payload, state in self.variants():
            for case in ('safety', 'scrimmage', 'onside', 'ready', 'before_touch',
                         'carrier', 'kicker', 'hidden', 'slot11', 'paired'):
                m = NativeMachine(payload, state_va=state, onside=case == 'onside')
                m.launch(); who = m.BLOCKER
                if case != 'before_touch':
                    m.position(0, 3600, m.RETURNER); m.event('touch')
                if case == 'safety': m.put(dk.PHASE, 1)
                if case == 'scrimmage': m.put(dk.PHASE, 4)
                if case == 'ready': m.put(dk.PLAY_STATE, 13)
                if case == 'carrier': m.put(m.BALL, who)
                if case == 'kicker': who = m.KICKER
                if case == 'hidden': m.put(who + 0x48, 1)
                if case == 'slot11': m.uc.mem_write(who + 0x2E, b'\x0b')
                if case == 'paired': m.put(who + 0xE38, m.get(who + 0xE38) | 2)
                m.run(0x23CE70, ecx=who, stop=0x23CE76)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ECX), who, case)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EBP), m.STACK - 4, case)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), (m.STACK - 4) & ~15, case)


class PublicReceiptTests(unittest.TestCase):
    def test_receipt_writers_and_complete_return_metrics(self):
        saved = json.loads(RECEIPT.read_text())
        self.assertTrue(saved['experimental']); self.assertFalse(saved['runtime_witnessed'])
        self.assertEqual((saved['executable']['code_allocation'], saved['executable']['state_allocation'],
                          saved['executable']['hook_count']), (1939, 10, 19))
        for key, case in saved['setup'].items():
            self.assertEqual(digest(case['trace']), case['trace_sha256'])
            self.assertEqual(len(case['trace']['frames']), 25)
            self.assertEqual(case['contact_moved_players'], list(HELD))
            pre = case['frames'][:20]
            samples = [row for row in case['foot_trace'] if 0 <= row[0] < 20 and row[2] != 0]
            self.assertEqual(len(samples), sum(row['foot_samples'] for row in pre))
            self.assertTrue(all(math.isfinite(value) for row in case['foot_trace']
                                for value in struct.unpack('<4f', bytes.fromhex(row[4]))))
            if key.startswith('v4'):
                self.assertEqual({row[1] for row in samples}, set(range(13, 22)))
                for p in range(13, 22):
                    self.assertEqual({row[0] for row in samples if row[1] == p}, set(range(20)))
            else:
                self.assertEqual(samples, [])
            for p in ('0', '11', '12'): self.assertGreater(case['free_changed_frames'][p], 0)
        for key, case in saved['returns'].items():
            self.assertEqual(len(case['states']), case['frames'])
            self.assertLessEqual(case['frames'], 900)
            carrier = case['carrier_index']
            self.assertIn(carrier, (11, 12))
            self.assertLessEqual(case['direction'] * case['states'][-1][carrier][1], -50 * 91.44)
            self.assertEqual(set(case['metrics']), {str(p) for p in range(11, 22) if p != carrier})
            for player, metrics in case['metrics'].items():
                targets = [t for _, p, t in case['pursuits'] if p == int(player)]
                self.assertEqual(metrics['pursuit_calls'], len(targets))
                self.assertEqual(metrics['kicker_pursuits'], targets.count(0))
                if not key.startswith('v4'):
                    self.assertEqual(metrics['kicker_pursuits'], 0)
                    self.assertEqual(metrics['passes_while_chasing_kicker'], 0)
                    self.assertEqual(metrics['lane_mismatches'], 0)
                    self.assertNotIn(0, metrics['contact_peers'])
        self.assertEqual(set(saved['returns']), {
            f'{name}_{direction:+d}_kr{slot}' for name in ('v4', 'legacy', 'grown')
            for direction in (-1, 1) for slot in (1, 2)})


def record():
    V5Tests.setUpClass(); test = V5Tests()
    result = dict(experimental=True, runtime_witnessed=False, executable=test.evidence, setup={}, returns={})
    for name, payload, state in [('v4', test.v4, dk.FLAGS)] + test.variants():
        for direction in (-1, 1):
            key = f'{name}_{direction:+d}'
            result['setup'][key] = setup_replay(test, payload, state, direction, historical=name == 'v4')
            print(key, 'setup complete', flush=True)
    for name, payload, state in [('v4', test.v4, dk.FLAGS)] + test.variants():
        for direction in (-1, 1):
            for carrier_slot in (0, 1):
                key = f'{name}_{direction:+d}_kr{carrier_slot + 1}'
                result['returns'][key] = return_replay(test, payload, state, direction, carrier_slot)
                print(key, 'return complete', result['returns'][key]['metrics'], flush=True)
    RECEIPT.write_text(json.dumps(result, separators=(',', ':')) + '\n', encoding='utf-8')


if __name__ == '__main__':
    record() if sys.argv[1:] == ['--record'] else unittest.main()
