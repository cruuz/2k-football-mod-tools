"""Standalone v3 complete-frame, exact-receipt and guard regression proofs.

Optional evidence refresh: python3 this_file.py --record
The normal unittest run only reads receipts and independently replays them.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_nfl2k5_dynamic_kickoff import RETAIL, PRIVATE_REASON, uni, x86, Cs
from tests.mod_editor.test_nfl2k5_kickoff_v2 import v2_payload
from tests.nfl2k5_kickoff_frame import FrameMachine, WriteReceipt, PHASES, FIELDS, SITES
from tests.nfl2k5_allocator_stack import REQUESTS
from mod_editor.core import nfl2k5_dynamic_kickoff as dk, nfl2k5_dynamic_kickoff_relocated as relocated
from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_kick_rules as kr
from mod_editor.core.nfl2k5_bump_strength import RETAIL_XBE_SHA256, _sections, section_digest

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / 'docs/nfl2k5_kickoff_v3_receipts.json'
TRACES = ROOT / 'docs/nfl2k5_kickoff_v3_frames.json'
HELD = tuple(range(1, 11)) + tuple(range(13, 22))


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


def fresh_collision_evidence(payload):
    m = FrameMachine(payload, radius=250)
    m.put(dk.PLAY_STATE, 14)
    frames = []
    for frame in range(3):
        state = m.frame()
        frames.append(dict(frame=frame,
                           position_additions=[e for e in m.writes if e[0] in HELD
                                               and e[3] in (0x1D898D, 0x1D8997)
                                               and e[5] != e[6]],
                           final_positions=[[p, state[p, 'transform'][0x30:0x40].hex()]
                                            for p in HELD]))
    return dict(radius=250, play_state=14, residual_seed=False, frames=frames)


def patch_evidence(retail):
    base = kr.apply(retail)[0]
    legacy, legacy_receipt = dk.apply(base)
    allocated = space.apply(legacy, REQUESTS, scaleout=True)[0]
    grown, grown_receipt = relocated.apply(allocated)
    result = dict(schema=1, experimental=True, runtime_witnessed=False,
                  retail_xbe_sha256=hashlib.sha256(retail).hexdigest(),
                  legacy_input_sha256=hashlib.sha256(base).hexdigest(),
                  legacy_output_sha256=hashlib.sha256(legacy).hexdigest(),
                  union_requests=REQUESTS,
                  union_allocated_sha256=hashlib.sha256(allocated).hexdigest(),
                  relocated_output_sha256=hashlib.sha256(grown).hexdigest(),
                  code_bytes_used=len(dk._code(dk._settings())[0].rstrip(b'\xcc')),
                  code_allocation=1939, state_allocation=10, hook_count=len(dk.HOOKS))
    for name, before, after, receipt in (('legacy', base, legacy, legacy_receipt),
                                        ('relocated', allocated, grown, grown_receipt)):
        result[name] = receipt
        edits = []
        for section in _sections(after):
            off = section.header_offset + 36
            if before[off:off + 20] != after[off:off + 20]:
                edits.append(dict(offset=off, before=before[off:off + 20].hex(),
                                  after=after[off:off + 20].hex()))
        result[name + '_section_digest_edits'] = edits
    # install_code updates exactly these two allocator seals in addition to
    # the section digests. Preserve them in the executable replay receipt.
    result['relocated_allocator_metadata_edits'] = [
        dict(offset=off, before=allocated[off:off + 32].hex(), after=grown[off:off + 32].hex())
        for off in (space.DIRECTORY + 20, space.SCALE_DIRECTORY + 12)]
    return (base, legacy, allocated, grown), result


def exercise(test, payload, *, state, direction, fixed, radius, release='touch'):
    m = FrameMachine(payload, state_va=state, direction=direction, radius=radius)
    m.seed_residuals()
    initial = m.snapshot()
    trace = WriteReceipt()
    previous = m.frame()  # frame 0: canonical idle entry, explicitly retained
    trace.add(m, previous)
    initial_held = {key: value for key, value in previous.items() if key[0] in HELD}
    changes, free_movement = [], Counter()
    for frame in range(1, 61):
        if frame == 21:
            m.put(dk.PLAY_STATE, 14)  # approach, before ball launch
        if frame == 41:
            m.launch()  # real launch hook/opcode, first-contact bits still clear
            test.assertEqual(m.flags() & 15, 8)
        current = m.frame()
        trace.add(m, current)
        delta = Counter(kind for (player, kind), value in current.items()
                        if player in HELD and previous[player, kind] != value)
        changes.append([delta[kind] for kind in FIELDS])
        if fixed:
            test.assertEqual(dict(delta), {}, f'held write survived frame {frame}')
            test.assertEqual({k: v for k, v in current.items() if k[0] in HELD}, initial_held)
        test.assertEqual(m.flags() & 7, 0, 'a frame/time change released the hold')
        test.assertEqual(m.get(dk.PLAY_STATE), 13 if frame < 21 else 14)
        test.assertEqual(m.get(0xB71D0C), struct.unpack('<I', struct.pack('<f', 1 / 60))[0])
        for player in (0, 11, 12):
            if current[player, 'transform'][0x30:0x40] != previous[player, 'transform'][0x30:0x40]:
                free_movement[player] += 1
        previous = current
    test.assertEqual(set(free_movement), {0, 11, 12})
    for phase in PHASES:
        test.assertEqual(m.visited[phase], 61)
        test.assertNotIn(phase, m.stub_pops)
    for pc in (0xDF9B0, 0xDFA50, 0xDFB40, 0xDF2F0, 0x93800, 0x214F60, 0xE0110):
        test.assertGreater(m.visited[pc], 0, hex(pc))
        test.assertNotIn(pc, m.stub_pops)
    if radius == 250:
        for pc in (0x304F60, 0x1DADD0, 0x1DD720):
            test.assertGreater(m.visited[pc], 0, hex(pc))
    if not fixed:
        for kind in ('transform', 'sampled_pose', 'skeleton_root', 'skeleton_high_root'):
            test.assertTrue(any(row[FIELDS.index(kind)] for row in changes), kind)
        test.assertTrue(any(e[3] == 0x28D06D and e[5] != e[6] for e in trace.events))
        test.assertTrue(any(e[3] == 0x28D081 and e[5] != e[6] for e in trace.events))
    held_visits = dict(m.visited)
    held_leaves = Counter(m.calls)
    before_contact = m.flags()
    m.position(0, direction * 3600, m.RETURNER)
    m.event(release)
    after_contact = m.flags()
    test.assertEqual(after_contact & 7, 1)
    released = m.frame()
    released_players = sorted(player for player in HELD
                              if released[player, 'transform'][0x30:0x40]
                              != previous[player, 'transform'][0x30:0x40])
    test.assertEqual(released_players, list(HELD))
    # The exact release frame is also retained, beyond the 60 held frames.
    trace.add(m, released)
    for who in m.held:
        test.assertNotEqual(m.readf(m.get(who + 0xC58) + 4), 0)
    return dict(
        direction=direction, fixed=fixed, radius=radius, held_frames=60,
        entry_frame=0, release_frame=61, phase_transition_frames=[21, 41],
        fields=list(FIELDS), held_player_indices=list(HELD),
        initial_positions=[[p, *struct.unpack('<3f', initial[p, 'transform'][0x30:0x3C])]
                           for p in range(22)],
        per_frame_changed_players=changes,
        free_position_change_frames={str(k): v for k, v in sorted(free_movement.items())},
        phase_calls={hex(k): held_visits[k] for k in PHASES},
        native_calls={hex(k): held_visits.get(k, 0) for k in sorted(SITES)},
        abi_leaf_calls={hex(k): v for k, v in sorted(held_leaves.items())},
        first_contact=dict(event=release, before=before_contact, after=after_contact,
                           moved_players=released_players),
        total_held_player_writes=sum(len(trace.sequences[s]) for s, _ in trace.frames),
        trace_sha256=trace.digest()), trace.result()


@unittest.skipUnless(RETAIL.is_file() and uni is not None and Cs is not None,
                     PRIVATE_REASON + '; unicorn/capstone required')
class V3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()  # ~12 MB XBE; never a disc or pack
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_XBE_SHA256:
            raise unittest.SkipTest('private retail XBE SHA-256 differs')
        cls.payloads, cls.patch_receipt = patch_evidence(cls.retail)
        cls.base, cls.legacy, cls.allocated, cls.grown = cls.payloads
        cls.v2 = v2_payload(cls.base)

    def variants(self):
        return [('legacy', self.legacy, dk.FLAGS),
                ('grown', self.grown, relocated._sites(self.grown)[1]['va'])]

    def test_exact_executable_receipts_and_foreign_v2_rejection(self):
        receipt = json.loads(RECEIPT.read_text())
        for key, value in self.patch_receipt.items():
            self.assertEqual(digest(value), digest(receipt[key]), key)
        for source, expected, name in ((self.base, self.legacy, 'legacy'),
                                        (self.allocated, self.grown, 'relocated')):
            replay = bytearray(source)
            edits = receipt[name]['edits'] + receipt[name + '_section_digest_edits']
            if name == 'relocated':
                edits += receipt['relocated_allocator_metadata_edits']
            for edit in edits:
                off, after = edit['offset'], bytes.fromhex(edit['after'])
                before = source[off:off + len(after)]
                if 'before' in edit:
                    self.assertEqual(before.hex(), edit['before'])
                else:
                    self.assertEqual(hashlib.sha256(before).hexdigest(), edit['before_sha256'])
                replay[off:off + len(after)] = after
            self.assertEqual(bytes(replay), expected)
            self.assertEqual(dk.status(expected), 'applied')
            self.assertEqual(dk.apply(expected)[0], expected)
            for section in _sections(expected):
                self.assertEqual(section.stored_digest, section_digest(expected, section))
        self.assertEqual(dk.status(self.v2), 'foreign')
        with self.assertRaises(ValueError):
            dk.apply(self.v2)
        for _, payload, _ in self.variants():
            va, original = dk.HOOKS['separation']
            off = dk._offset(payload, va, len(original))
            mixed = bytearray(payload)
            mixed[off:off + len(original)] = original
            before = bytes(mixed)
            self.assertEqual(dk.status(before), 'foreign')
            with self.assertRaises(ValueError):
                dk.apply(before)
            self.assertEqual(bytes(mixed), before)

    def test_complete_60_frames_all_roles_directions_placements_and_contact(self):
        receipt = json.loads(RECEIPT.read_text())
        for placement, payload, state in self.variants():
            for direction in (-1, 1):
                key = f'{placement}_{direction:+d}'
                with self.subTest(case=key):
                    summary, trace = exercise(self, payload, state=state, direction=direction,
                                              fixed=True, radius=250,
                                              release='ground' if direction < 0 else 'touch')
                    self.assertEqual(summary, receipt['cases'][key])
                    self.assertEqual(digest(trace), summary['trace_sha256'])

    def test_historical_v2_full_frame_counterexample(self):
        summary, _ = exercise(self, self.v2, state=dk.FLAGS, direction=1,
                              fixed=False, radius=30)
        self.assertEqual(summary, json.loads(RECEIPT.read_text())['cases']['v2_counterexample'])

    def test_separate_residual_turn_and_collision_counterexamples(self):
        for turn, separation in ((True, False), (False, True)):
            m = FrameMachine(self.v2, tasks=False)
            m.seed_residuals(turn=turn, separation=separation)
            first, second = m.frame(), m.frame()
            if turn:
                self.assertEqual(first[1, 'transform'], second[1, 'transform'])
                self.assertNotEqual(first[1, 'skeleton_root'][:48], second[1, 'skeleton_root'][:48])
            else:
                self.assertNotEqual(first[1, 'transform'], second[1, 'transform'])
                self.assertEqual(first[1, 'skeleton_root'][:48], second[1, 'skeleton_root'][:48])
                self.assertTrue(any(e[3] in (0x28D06D, 0x28D081) and e[5] != e[6]
                                    for e in m.writes if e[0] == 1))
        # A fresh native collision in approach writes position without going
        # through either v2 guard. No residual impulse or spring is seeded.
        fresh = fresh_collision_evidence(self.v2)
        self.assertEqual(digest(fresh), digest(json.loads(RECEIPT.read_text())['fresh_collision_counterexample']))
        first, second = fresh['frames'][:2]
        self.assertNotEqual(first['final_positions'], second['final_positions'])
        for pc in (0x1D898D, 0x1D8997):
            self.assertTrue(any(e[3] == pc for e in second['position_additions']))

    def test_collision_producer_guard_preserves_abi_and_unheld_behavior(self):
        for _, payload, state in self.variants():
            m = FrameMachine(payload, state_va=state, tasks=False)
            displacement = m.CONTACT + 0x200
            m.uc.mem_write(displacement, struct.pack('<4f', 12, 0, -8, 0))
            m.put(m.COVERAGE + 0x100, 0)  # selected human coverage is held too
            for label, who, held in [('coverage', m.COVERAGE, True),
                                      ('setup', m.BLOCKER, True),
                                      ('kicker', m.KICKER, False),
                                      ('returner_0', m.players[11], False),
                                      ('returner_1', m.players[12], False)]:
                with self.subTest(role=label, state=state):
                    before = bytes(m.uc.mem_read(who + 0xB30, 16))
                    m.uc.reg_write(x86.UC_X86_REG_EAX, who)
                    m.run(0x1D8940, args=(displacement,))
                    self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP), m.STACK + 8)
                    after = bytes(m.uc.mem_read(who + 0xB30, 16))
                    if held:
                        self.assertEqual(after, before)
                    else:
                        x, y, z, w = struct.unpack('<4f', before)
                        self.assertEqual(struct.unpack('<4f', after), (x + 12, y, z - 8, w))
            # Form, phase, active-list and first-contact exclusions all replay
            # the native producer, including its collision bookkeeping.
            for address, value in ((dk.PHASE, 1), (dk.PHASE, 0), (dk.PLAY_STATE, 12),
                                    (m.KICK_BOOK + 0x204, 10 << 8),
                                    (m.COVERAGE + 0x48, 1), (state, 1)):
                saved = m.get(address)
                m.put(address, value)
                before = m.readf(m.COVERAGE + 0xB30)
                m.uc.reg_write(x86.UC_X86_REG_EAX, m.COVERAGE)
                m.run(0x1D8940, args=(displacement,))
                self.assertEqual(m.readf(m.COVERAGE + 0xB30), before + 12)
                m.put(address, saved)

    def test_gate_projection_keeps_unknown_ownership_fail_closed(self):
        import copy
        from tests.nfl2k5_allocator_stack import manifest_for_allocated_union, music, SONGS
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        original = ReservationManifest.load(Path(DEFAULT_MANIFEST), XbeImage(self.retail))
        # Match the gate's separate music RO section as well as REQUESTS.
        with_music = music.apply(self.grown, SONGS)[0]
        projected = manifest_for_allocated_union(original, self.retail, with_music)
        va, pin = dk.HOOKS['separation']
        self.assertTrue(projected.overlaps(va, va + len(pin)))
        damaged = copy.deepcopy(original.document)
        span = next(s for s in damaged['spans']
                    if s['owner'] == 'nfl2k5_camera' and int(s['start'], 0) >= space.CODE_VA)
        span['owner'] = 'unrecognized_camera_owner'
        unknown = ReservationManifest(damaged, XbeImage(self.retail))
        with self.assertRaisesRegex(AssertionError, 'unrecognized grown owner'):
            manifest_for_allocated_union(unknown, self.retail, with_music)


class ReceiptIntegrityTests(unittest.TestCase):
    def test_lossless_write_log_and_frame_states_without_private_assets(self):
        receipt = json.loads(RECEIPT.read_text())
        raw = TRACES.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt['frame_file_sha256'])
        traces = json.loads(raw)
        for name, trace in traces.items():
            self.assertEqual(digest(trace), receipt['cases'][name]['trace_sha256'])
            self.assertEqual(len(trace['frames']), 62)
            self.assertEqual(sum(len(trace['sequences'][s]) for s, _ in trace['frames']),
                             receipt['cases'][name]['total_held_player_writes'])
            for event in trace['events']:
                player, field, phase, pc, off, before, after = event
                self.assertIn(player, HELD)
                self.assertIn(field, FIELDS)
                self.assertIn(phase, PHASES)
                self.assertEqual(len(before), len(after))
                self.assertIn(len(bytes.fromhex(after)), (1, 2, 4, 8))
                self.assertGreater(pc, 0)
                self.assertGreaterEqual(off, 0)
            if name != 'v2_counterexample':
                self.assertEqual(len({state for _, state in trace['frames'][:61]}), 1)


def record():
    V3Tests.setUpClass()
    test = V3Tests()
    result = V3Tests.patch_receipt
    result['cases'] = {}
    result['fresh_collision_counterexample'] = fresh_collision_evidence(V3Tests.v2)
    traces = {}
    cases = [('v2_counterexample', V3Tests.v2, dk.FLAGS, 1, False, 30)]
    cases += [(f'{name}_{direction:+d}', payload, state, direction, True, 250)
              for name, payload, state in test.variants() for direction in (-1, 1)]
    for name, payload, state, direction, fixed, radius in cases:
        summary, trace = exercise(test, payload, state=state, direction=direction,
                                  fixed=fixed, radius=radius,
                                  release='ground' if direction < 0 else 'touch')
        result['cases'][name], traces[name] = summary, trace
        print(name, summary['total_held_player_writes'], 'writes', flush=True)
    raw = (json.dumps(traces, separators=(',', ':')) + '\n').encode()
    result['frame_file_sha256'] = hashlib.sha256(raw).hexdigest()
    TRACES.write_bytes(raw)
    RECEIPT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    if sys.argv[1:] == ['--record']:
        record()
    else:
        unittest.main()
