"""Screen data experiments: standalone, no display, game boot or image writes."""
from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'tools'))

from mod_editor.core import nfl2k5_screen_timing as timing
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_formation_play_writer as writer
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core.errors import ValidationError

EXTRACTION = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
    '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)'


def retail_books():
    index = EXTRACTION / 'vc_53450030' / '0'
    if not index.is_file():
        raise unittest.SkipTest('Retail extracted vc_53450030/0 and its archive packs are absent')
    from nfl_outer import parse_archive, read_entry_bytes
    arc = parse_archive(index)
    return {i: read_entry_bytes(arc, arc.entries[i])[:32 + insp.BODY_SIZE] for i in range(307, 344)}


def spec_for(variant='HB', slot=None, side=-1, level='D'):
    return lib.PlaySpec('Experimental screen', 'pass',
        [(0, -91), (304, 0), (-304, 0), (0, 0), (152, 0), (-152, 0),
         (457, 0), (-1371, -219), (1371, -219), (457, -300), (0, -640)],
        [lib.QB, lib.T, lib.T, lib.C, lib.G, lib.G, lib.TE, lib.WR, lib.WR, lib.FB, lib.HB], {},
        screen=lib.screen_preset(variant, slot, side, level))


def encoded(chain):
    nodes = [codec.Node(op, 0, list(vals)) for op, vals in chain]
    codec.assign_node_flags(nodes)
    return [node.to_bytes() for node in nodes]


class ScreenAuthorUnitTests(unittest.TestCase):
    def test_variants_slots_timing_and_protection(self):
        for variant, slot in [('HB', 10), ('WR', 7), ('WR', 8), ('TE', 6)]:
            for side in (-1, 1):
                with self.subTest(variant=variant, slot=slot, side=side):
                    spec = spec_for(variant, slot, side)
                    lib.default_assignments(spec, variant + ' Screen')
                    chains = lib.build_chains(spec)
                    releasing = [s for s in range(11) if spec.assignments[s].kind == 'screen_release']
                    self.assertEqual(releasing, [2, 3, 5] if side < 0 else [1, 3, 4])
                    for s in releasing:
                        ns = [codec.Node.from_bytes(n) for n in encoded(chains[s])]
                        self.assertEqual([n.op for n in ns[-3:]], [17, 24, 17])
                        self.assertEqual(ns[-3].operands[1], .8)
                        self.assertEqual(ns[-1].operands[0], 3)
                        self.assertEqual(ns[-2].operands[1] > 0, side > 0)
                    self.assertEqual(chains[3][1], (2, [0]))
                    self.assertEqual(chains[0][-1][1], [5, slot - 5, 0, 0, 0, .6])
                    self.assertEqual(chains[0][2][1][2], -7 * lib.YD)
                    self.assertEqual(chains[slot][-1][1][0], 9)
                    self.assertEqual(chains[slot][-1][1][2], 11 * side * lib.YD)
                    for s in set(range(1, 6)) - set(releasing):
                        self.assertEqual([op for op, vals in chains[s]], [1, 17])
                        self.assertEqual(chains[s][-1][1][1], 0)
                    self.assertEqual(writer.authored_node_cost(chains), 31)

    def test_missing_receiver_invalid_timing_and_pa_refuse(self):
        for variant, slot in [('TE', 7), ('HB', 3), ('WR', 10)]:
            with self.assertRaisesRegex(ValueError, 'assignment slot'):
                lib.default_assignments(spec_for(variant, slot), variant + ' Screen')
        for value in (0, -.1, float('nan'), 6.4):
            spec = spec_for(); spec.screen.hold_seconds = value
            with self.assertRaisesRegex(ValueError, 'finite hold'):
                lib.default_assignments(spec, 'HB Screen')
        spec = spec_for(); spec.play_type = 'pa_pass'
        with self.assertRaisesRegex(ValueError, 'Pass play type'):
            lib.default_assignments(spec, 'HB Screen')

    def test_endpoint_adjustment_both_directions_and_types(self):
        for direction in (-1, 1):
            for x in (-3000, -1798.32, -500, 0, 1798.32, 3000):
                self.assertEqual(lib.screen_endpoint(x, 0, 9, direction, 100),
                                 (max(-1798.32, min(1798.32, x)), 100 - direction * 1.5 * lib.YD))
                self.assertEqual(lib.screen_endpoint(x, 2000, 9, direction)[0], 2000)
                self.assertEqual(lib.screen_endpoint(x, -2000, 9, direction)[0], -2000)
                self.assertEqual(lib.screen_endpoint(x, 0, 10, direction), (x, -direction * lib.YD))

    def test_unknown_payload_and_level_refuse(self):
        self.assertEqual(timing.status(b'not a playbook'), 'foreign')
        with self.assertRaises(ValidationError):
            timing.apply(b'not a playbook')
        for level in ('', 'a', None, 'Retail'):
            with self.assertRaisesRegex(ValidationError, 'A, B, C or D'):
                timing.status(b'', level)

    def test_cost_enforces_runtime_length(self):
        self.assertEqual(writer.authored_node_cost([None] * 11), 0)
        for chains in ([None] * 10, [[]] + [None] * 10, [[None] * 16] + [None] * 10):
            with self.assertRaises(ValidationError):
                writer.authored_node_cost(chains)


class RetailScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.books = retail_books()

    def test_all_37_books_four_levels_idempotence_receipts_and_validation(self):
        totals = Counter()
        for outer, raw in self.books.items():
            before = insp.parse_playbook_resource(raw)
            for level in timing.LEVELS:
                with self.subTest(outer=outer, level=level):
                    patched, receipt = timing.apply(raw, level)
                    again, repeat = timing.apply(patched, level)
                    self.assertEqual(len(patched), len(raw))
                    self.assertEqual(again, patched)
                    self.assertEqual(repeat['changed_bytes'], 0)
                    self.assertEqual(repeat['nodes_added'], 0)
                    self.assertEqual(timing.status(patched, level), 'applied')
                    self.assertEqual(receipt['outer_index'], outer)
                    self.assertEqual(receipt['book'], before.book_name)
                    self.assertEqual(receipt['changed_bytes'], sum(a != b for a, b in zip(raw, patched)))
                    replay = bytearray(raw)
                    for change in receipt['changes']:
                        pos = change['offset']; old = bytes.fromhex(change['before']); new = bytes.fromhex(change['after'])
                        self.assertEqual(raw[pos:pos + len(old)], old)
                        replay[pos:pos + len(old)] = new
                    self.assertEqual(replay, patched)
                    owned = sum(p['changed_bytes'] for p in receipt['plays'])
                    shared = sum(len(c['after']) // 2 for c in receipt['shared_changes'])
                    self.assertEqual(owned + shared, receipt['changed_bytes'])
                    after = insp.parse_playbook_resource(patched)
                    self.assertEqual(after.formations, before.formations)
                    for play in after.plays:
                        flags, chains = lib.play_chains(patched[32:], play.index)
                        self.assertIsNone(codec.validate_play(flags, chains), (outer, level, play.index))
                    totals[level] += sum(bool(p['changed_slots']) for p in receipt['plays'])
        self.assertEqual(dict(totals), {'A': 61, 'B': 61, 'C': 64, 'D': 64})

    def test_census_skips_and_capacity(self):
        count = eligible = 0
        capacities = []
        for raw in self.books.values():
            info = timing.inspect(raw)
            count += len(info['plays'])
            eligible += sum(bool(p['release_slots']) for p in info['plays'])
            capacities.append(info['remaining_nodes'])
            self.assertTrue(info['capacity_ok'])
            self.assertGreaterEqual(info['remaining_nodes'], info['nodes_added'])
        self.assertEqual((count, eligible, min(capacities)), (129, 64, 761))
        skipped = {p['play_index'] for p in timing.inspect(self.books[335])['plays'] if not p['release_slots']}
        self.assertEqual(skipped, {196, 197})

    def test_archive_round_trip_with_real_books(self):
        from tests.mod_editor.test_nfl2k5_screen_archive import MemoryArchive
        archive = MemoryArchive(self.books)
        self.assertEqual(timing.inspect_archive(archive)['status'], 'retail')
        receipt = timing.apply_to_archive(archive)
        self.assertEqual(len(receipt['books']), 37)
        self.assertEqual(timing.inspect_archive(archive)['status'], 'applied')
        writes = archive.writes
        self.assertEqual(timing.apply_to_archive(archive)['changed_bytes'], 0)
        self.assertEqual(archive.writes, writes)
        self.assertEqual(sum(book['changed_bytes'] for book in receipt['books']), receipt['changed_bytes'])

    def test_atl_measured_bytes_shared_chains_and_orphan_extent(self):
        raw = self.books[308]; before = insp.parse_playbook_resource(raw)
        for level, nodes, changed in [('A', 13, 74), ('B', 4, 16), ('C', 4, 17), ('D', 17, 90)]:
            patched, receipt = timing.apply(raw, level)
            self.assertEqual((receipt['nodes_added'], receipt['changed_bytes']), (nodes, changed))
            after = insp.parse_playbook_resource(patched)
            self.assertEqual([f.index for f in before.formations if any(l.play_index == 178 for l in f.play_links)],
                             [f.index for f in after.formations if any(l.play_index == 178 for l in f.play_links)])
            for play in before.plays:
                for slot, assignment in enumerate(play.assignments):
                    if play.index == 178 and slot in ({2, 3, 5} if level == 'A' else {0} if level in ('B', 'C') else {0, 2, 3, 5}):
                        continue
                    self.assertEqual(after.plays[play.index].assignments[slot], assignment)
                    self.assertEqual(before.assignment_chain(assignment), after.assignment_chain(assignment))
            if level != 'A':
                assignment = after.plays[177].assignments[-1]
                self.assertGreater(after.chain(assignment.chain_start_index).node_count, assignment.declared_length)

    def test_foreign_mixed_other_level_and_skipped_screen_refuse(self):
        raw = self.books[308]
        wrapper_edit = bytearray(raw); wrapper_edit[8] ^= 1
        self.assertEqual(timing.status(wrapper_edit), 'foreign')
        with self.assertRaisesRegex(ValidationError, 'wrapper'):
            timing.apply(wrapper_edit)
        book = insp.parse_playbook_resource(raw)
        for play_index in (178, 170):
            damaged = bytearray(raw)
            a = book.plays[play_index].assignments[0]
            damaged[32 + insp.NODE_BASE + (a.chain_start_index + 2) * 8 + 7] ^= 1
            self.assertEqual(timing.status(damaged), 'foreign')
            saved = bytes(damaged)
            with self.assertRaises(ValidationError): timing.apply(damaged)
            self.assertEqual(bytes(damaged), saved)
        applied, _ = timing.apply(raw, 'A')
        self.assertEqual(timing.status(applied, 'D'), 'foreign')
        with self.assertRaises(ValidationError): timing.apply(applied, 'D')
        mixed = bytearray(timing.apply(raw, 'D')[0])
        pos = 32 + insp.PLAY_BASE + 178 * insp.PLAY_SIZE + 8
        mixed[pos:pos + 8] = raw[pos:pos + 8]
        self.assertEqual(timing.status(mixed), 'foreign')
        with self.assertRaises(ValidationError): timing.apply(mixed)

    def test_node_capacity_and_foreign_tail_refuse_without_mutation(self):
        raw = self.books[308]
        for count, message in [(writer.NODE_CAPACITY - 1, 'insufficient nodes'), (2438, 'padding')]:
            damaged = bytearray(raw)
            if count == 2438:
                damaged[32 + insp.NODE_BASE + count * 8] = 1
            else:
                # Extend the orphan tail with complete terminal nodes so parser remains valid.
                terminal = raw[32 + insp.NODE_BASE + 2437 * 8:32 + insp.NODE_BASE + 2438 * 8]
                damaged[32 + insp.NODE_BASE + 2438 * 8:32 + insp.NODE_BASE + count * 8] = terminal * (count - 2438)
                struct.pack_into('<I', damaged, 32 + 0x40, count)
            saved = bytes(damaged)
            with self.assertRaisesRegex(ValidationError, message): timing.apply(damaged)
            self.assertEqual(saved, damaged)

    def test_retail_author_matches_donor_and_all_variants_compile(self):
        raw = self.books[308]
        donor_flags, donor = lib.play_chains(raw[32:], 178)
        spec = spec_for(level='Retail')
        lib.default_assignments(spec, 'HB Screen'); chains = lib.build_chains(spec)
        for slot in (0, 2, 3, 5, 10):
            self.assertEqual(encoded(chains[slot]), donor[slot][1])
        self.assertEqual(sum(len(chains[s]) for s in (0, 2, 3, 5, 10)), 19)
        for variant, slot in [('HB', 10), ('WR', 7), ('WR', 8), ('TE', 6)]:
            for side in (-1, 1):
                spec = spec_for(variant, slot, side)
                lib.default_assignments(spec, variant + ' Screen'); chains = lib.build_chains(spec)
                compiled = writer.compile_formation_play_creations(raw, play_requests=[{
                    'asset_id': 'private.PLAY', 'donor_play_index': 178, 'replace_index': 178,
                    'assignments': chains}])
                self.assertEqual(compiled.report['new_node_count'] - 2438, writer.authored_node_cost(chains))
                flags, actual = lib.play_chains(compiled.replacement[32:], 178)
                self.assertIsNone(codec.validate_play(flags, actual))
                self.assertEqual(actual[slot][1][-1], encoded(chains[slot])[-1])

    def test_category_recode_composes_and_xbe_is_refused(self):
        from mod_editor.core import nfl2k5_depth_roles as roles
        raw = self.books[308]
        recoded = roles.normalise(raw).replacement
        patched, _ = timing.apply(recoded)
        expected = roles.normalise(timing.apply(raw)[0]).replacement
        self.assertEqual(patched, expected)
        xbe = EXTRACTION / 'default.xbe'
        if xbe.is_file():
            data = xbe.read_bytes()
            self.assertEqual(timing.status(data), 'foreign')
            with self.assertRaises(ValidationError): timing.apply(data)


if __name__ == '__main__':
    unittest.main()
