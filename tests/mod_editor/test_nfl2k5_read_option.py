"""Data-only option acceptance. Run standalone; retail evidence is read only.

No emulator or bounded execution is used here. Byte fidelity is not gameplay.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / 'tools'):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_pack as pk
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_formation_play_writer as writer
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_nfl2k5_defense_play import retail_resources

SEED = ROOT / 'data/playbooks/softdrink_option.2k5book'


def raw_chains(chains):
    return [(0, [n.to_bytes() for n in codec.encode_chain(c)]) for c in chains]


def swap_backs():
    order = list(range(11))
    order[9], order[10] = order[10], order[9]
    return order


class OptionOfflineTests(unittest.TestCase):
    def test_explicit_and_legacy_stock_graphs_have_exact_flags(self):
        for weak in (False, True):
            chains = lib.stock_speed_option_chains(weak)
            for slot, flags in ((0, [0x10, 0x10, 0x14, 0x12, 0x13]),
                                (10, [0x10, 0x14, 0x02, 0x11, 0x03])):
                self.assertEqual([n.flags for n in codec.encode_chain(chains[slot])], flags)
                legacy = [n[:2] for n in chains[slot]]
                self.assertEqual([n.flags for n in codec.encode_chain(legacy)], flags)
            codec.validate_sync(raw_chains(chains))

    def test_bad_rows_finite_values_and_chain_budgets_refuse(self):
        for bad in ([], [None], [3], [[1]], [[True, []]], [[29, []]], [[25, []]],
                    [[1, None]], [[1, [float('nan')]]], [[1, [float('inf')]]],
                    [[1, [True]]], [[1, [], True]], [[1, [], 256]],
                    [[1, []]] * 16, [[26, [4]]]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                codec.encode_chain(bad)
        self.assertEqual(len(codec.encode_chain([[1, []]] * 15)), 15)

    def test_fork_indices_terminals_and_selectors_cannot_silently_wrap(self):
        chain = lib.stock_speed_option_chains()[0]
        for operand, value in ((0, 8), (3, 11), (3, -1), (4, 0), (4, 3), (4, 5),
                               (4, 8), (4, 4.5), (5, 2), (6, 16), (7, 2),
                               (1, 128 * codec.FT_CM), (2, 192 * codec.FT_CM)):
            bad = deepcopy(chain); bad[3][1][operand] = value
            with self.subTest(operand=operand, value=value), self.assertRaises(ValueError):
                codec.encode_chain(bad)
        for index, flags in ((2, 0x16), (3, 0x10), (4, 0x12)):
            bad = deepcopy(chain); bad[index] = (*bad[index][:2], flags)
            with self.assertRaises(ValueError):
                codec.encode_chain(bad)
        bad = deepcopy(chain); bad[0] = bad[0][:2]
        with self.assertRaisesRegex(ValueError, 'every flag'):
            codec.encode_chain(bad)
        # A 15-node descriptor does not enlarge the condition/cache index width.
        late = [codec.Node(1, 0, [1, 3, 0, 0, 0, 0]) for _ in range(8)]
        late += [codec.Node(26, 0, [4, 0, 0, 10, 9, 0, 13, 0]), codec.Node(19, 0, [10, 1])]
        with self.assertRaises(ValueError):
            codec.assign_node_flags(late)

    def test_synchronization_requires_friendly_condition_source(self):
        for operand, value in ((3, 9), (5, 1), (6, 2), (6, 8)):
            chains = lib.stock_speed_option_chains(); chains[10][1][1][operand] = value
            with self.subTest(operand=operand), self.assertRaises(ValueError):
                codec.validate_sync(raw_chains(chains))
        chains = lib.stock_speed_option_chains()
        chains[10][1][1][3] = 10
        chains[10][1][1][6] = 1
        with self.assertRaisesRegex(ValueError, 'cycle'):
            codec.validate_sync(raw_chains(chains))

    def test_retarget_uses_friendly_namespace_and_preserves_cache_index(self):
        for kind in (0, 1, 2, 3, 4, 5, 6, 7):
            for opponent in (0, 1):
                chains = lib.stock_speed_option_chains()
                chains[0][3][1][0] = kind
                chains[0][3][1][5] = opponent
                moved = pk.permute_assignments(chains, swap_backs())
                self.assertEqual(moved[0][3][1][3], 10 if opponent else 9)
                self.assertEqual(moved[0][4][1][0], 9)
                self.assertEqual(moved[9][1][1][6], 3)
                self.assertEqual(moved[0][3][2], 0x12)
        # Mode-2 follow movement also names a friendly actor.
        chains[10][2][1][5] = 9
        moved = pk.permute_assignments(chains, swap_backs())
        self.assertEqual(moved[9][2][1][5], 10)

    def test_mirror_is_an_involution_and_marks_both_branches(self):
        original = lib.stock_speed_option_chains()
        mirrored = lib.mirror_option_chains(original)
        self.assertEqual(raw_chains(lib.mirror_option_chains(mirrored)), raw_chains(original))
        self.assertAlmostEqual(mirrored[0][3][1][1], -original[0][3][1][1])
        self.assertEqual(mirrored[0][3][1][3:], original[0][3][1][3:])
        art = codec.play_art(codec.encode_chain(original[0]), (0, 0))
        mark = next(s for s in art if s.end_marker == 'branch')
        self.assertIn('Friendly slot 10', mark.label)
        self.assertIn('alternate node 4', mark.label)

    def test_seed_schema_round_trip_and_offline_budget(self):
        pack = pk.load_pack(SEED)
        self.assertEqual(pack.schema, pk.OPTION_SCHEMA)
        self.assertEqual(pk.loads_pack(pack.dumps()), pack)
        self.assertTrue(pk.check_pack(pack).ok)
        self.assertEqual((len(pack.plays), len(pack.formations)), (8, 0))
        self.assertTrue(all(p.replace_index is not None for p in pack.plays))
        self.assertEqual(pk.budget_totals(pack)['cloned_nodes'], 71)
        for schema in (pk.SCHEMA, pk.DEFENSE_SCHEMA):
            doc = pack.to_json(); doc['schema'] = schema
            with self.assertRaises(pk.PlaybookPackError):
                pk.pack_from_json(doc)
        doc = pack.to_json(); doc['plays'][0]['replace_index'] = None
        with self.assertRaisesRegex(pk.PlaybookPackError, 'replace existing'):
            pk.pack_from_json(doc)
        full = replace(pack, base=replace(pack.base, donor_node_count=3430))
        self.assertFalse(pk.check_pack(full).ok)

    def test_intent_schema_and_provider_identity(self):
        play = pk.load_pack(SEED).plays[-1]
        row = play.request_mapping('book:MIN')
        parsed = writer.play_request_from_mapping(row)
        self.assertEqual(writer.play_request_from_mapping(parsed.provider_edit()), parsed)
        changed = deepcopy(row); changed['option_intent']['opponent']['slot'] = 7
        self.assertNotEqual(writer.play_request_from_mapping(changed).selector, parsed.selector)
        for key, value in (('schema', 'foreign'), ('back_slot', True), ('receiver_slot', 9)):
            bad = deepcopy(play.option_intent); bad[key] = value
            with self.assertRaises(ValueError):
                lib.option_intent_from(bad)
        bad = deepcopy(play.option_intent); bad['opponent']['signature'] = 'foreign'
        with self.assertRaises(ValueError):
            lib.option_intent_from(bad)


class OptionRetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = retail_resources()
        cls.books = {t: insp.parse_playbook_resource(r, asset_id='book:' + t) for t, r in cls.resources.items()}

    def test_all_9251_retail_graphs_and_sync_references_are_accepted(self):
        count = 0
        for team, r in self.resources.items():
            for play in self.books[team].plays:
                flags, assignments = lib.play_chains(r[32:], play.index)
                codec.validate_sync(assignments)
                self.assertIsNone(codec.validate_play(flags, assignments), (team, play.index))
                count += 1
        self.assertEqual(count, 9251)

    def test_five_stock_options_clone_reauthor_mirror_retarget_export_import(self):
        for team, pi in lib.STOCK_SPEED_OPTIONS:
            r, book = self.resources[team], self.books[team]
            flags, original = lib.play_chains(r[32:], pi)
            recipe = lib.stock_speed_option_chains((team, pi) == ('NO', 66))
            self.assertEqual([n for _, n in raw_chains(recipe)], [n for _, n in original])
            clone = writer.compile_formation_play_creations(r, [], [writer.PlayCreateRequest(book.asset_id, pi, 'Option clone', replace_index=pi)])
            self.assertEqual(lib.play_chains(clone.replacement[32:], pi), (flags, original))
            self.assertEqual(clone.report['new_node_count'], book.node_count)
            chains = lib.decoded_chains(r[32:], pi)
            for mode, authored in (('explicit', chains), ('legacy', [[n[:2] for n in c] for c in chains]),
                                   ('mirror', lib.mirror_option_chains(chains)),
                                   ('retarget', pk.permute_assignments(chains, swap_backs()))):
                with self.subTest(team=team, pi=pi, mode=mode):
                    req = writer.PlayCreateRequest(book.asset_id, pi, 'Option round trip', assignments=authored, replace_index=pi)
                    req = writer.play_request_from_mapping(req.provider_edit())
                    compiled = writer.compile_formation_play_creations(r, [], [req])
                    out_flags, out = lib.play_chains(compiled.replacement[32:], pi)
                    self.assertEqual(out_flags, flags)
                    self.assertIsNone(codec.validate_play(out_flags, out))
                    codec.validate_sync(out)
                    self.assertEqual(len(compiled.replacement), len(r))
                    self.assertEqual(compiled.report['new_play_count'], len(book.plays))
                    self.assertEqual(compiled.report['new_node_count'] - book.node_count, 30)
                    if mode in ('explicit', 'legacy'):
                        self.assertEqual(out, original)  # descriptors AND all 30 node bytes
                    if mode == 'retarget':
                        self.assertEqual(codec.Node.from_bytes(out[0][1][3]).operands[3], 9)
                        self.assertEqual(codec.Node.from_bytes(out[0][1][4]).operands[0], 9)
                        self.assertEqual(out[9][1], original[10][1])
                    if mode == 'mirror':
                        expected = [[codec.Node.from_bytes(n, mirror=True).to_bytes() for n in c] for _, c in original]
                        self.assertEqual([c for _, c in out], expected)
                    exported = pk.pack_from_staged_rows(team=team, book=book, body=r[32:], play_rows=[req.provider_edit()])
                    exported = pk.loads_pack(exported.dumps())
                    rebuilt = pk.apply_pack_to_resource(r, exported)
                    self.assertEqual(rebuilt.replacement, compiled.replacement)
                    for a in rebuilt.parsed_replacement.plays[pi].assignments:
                        self.assertEqual(len(rebuilt.parsed_replacement.assignment_chain(a).nodes), a.declared_length)
            condition = book.assignment_chain(book.plays[pi].assignments[0]).nodes[3]
            self.assertEqual(condition.condition['alternate_index'], 4)
            self.assertEqual(condition.condition['actor_slot'], 10)
            self.assertTrue(condition.condition['human_input'])
            self.assertIn('Position / velocity', condition.description)
            self.assertIn('flags=0x12', condition.description)

    def test_flattened_negative_control_still_passes_retail_port_but_writer_refuses(self):
        r = self.resources['MIN']; flags, assignments = lib.play_chains(r[32:], 24)
        flat = []
        for desc, raw in assignments:
            nodes = [codec.Node.from_bytes(n) for n in raw]
            for n in nodes:
                n.flags &= ~3
            nodes[-1].flags |= 2
            flat.append((desc, [n.to_bytes() for n in nodes]))
        flat = [(codec.build_descriptor(flags, flat, s, desc >> 24), raw) for s, (desc, raw) in enumerate(flat)]
        self.assertIsNone(codec.validate_play(flags, flat))
        with self.assertRaisesRegex(ValueError, 'terminal|alternate'):
            codec.validate_sync(flat)
        authored = [codec.authored_chain([codec.Node.from_bytes(n) for n in c]) for _, c in flat]
        with self.assertRaises(ValidationError):
            writer.compile_formation_play_creations(r, [], [writer.PlayCreateRequest('book:MIN', 24, assignments=authored, replace_index=24)])

    def test_presets_all_directions_backs_and_receivers_compile(self):
        r, b = self.resources['MIN'], self.books['MIN']
        fi = next(f.index for f in b.formations if f.name == 'I Jokers')
        dfi = next(f.index for f in b.formations if f.name == '4-3')
        for preset in lib.OPTION_PRESETS:
            for weak in (False, True):
                for back in (9, 10):
                    for receiver in ((6, 7, 8) if preset == lib.OPTION_PRESETS[2] else (7,)):
                        with self.subTest(preset=preset, weak=weak, back=back, receiver=receiver):
                            d = lib.make_option_design(b, r[32:], fi, preset, weak=weak, back_slot=back,
                                                       opponent_formation_index=dfi, read_slot=2, receiver_slot=receiver)
                            req = writer.PlayCreateRequest(b.asset_id, d.donor_play_index, assignments=d.chains,
                                replace_index=24, play_flags=d.play_flags, option_intent=d.intent)
                            compiled = writer.compile_formation_play_creations(r, [], [req])
                            receipt = compiled.report['option_intent']['records'][0]
                            self.assertEqual(receipt['intent'], d.intent)
                            self.assertFalse(receipt['runtime_target_check'])
                            _, a = lib.play_chains(compiled.replacement[32:], 24)
                            codec.validate_sync(a)
                            if preset == lib.OPTION_PRESETS[2]:
                                self.assertEqual(codec.Node.from_bytes(a[0][1][3]).operands[1:5], [receiver - 5, 0, 0, 0])
                            self.assertLessEqual(max(len(c) for c in d.chains), 7)

    def test_pack_pipeline_exact_replacements_receipts_and_request_reload(self):
        r, b = self.resources['MIN'], self.books['MIN']
        pack = pk.option_pack(b, r[32:])
        self.assertEqual(pk.load_pack(SEED), pack)
        check = pk.check_pack(pack, resource=r)
        self.assertTrue(check.ok, check.errors)
        out = pk.apply_pack_to_resource(r, pack)
        self.assertEqual((out.report['new_play_count'], out.report['new_formation_count'], out.report['new_node_count']), (266, 46, 2543))
        self.assertEqual(out.replacement[:32], r[:32])
        self.assertEqual(out.replacement[32 + insp.FORMATION_BASE:32 + insp.PLAY_BASE], r[32 + insp.FORMATION_BASE:32 + insp.PLAY_BASE])
        for p in b.plays:
            if p.index not in {p.replace_index for p in pack.plays}:
                self.assertEqual(lib.play_chains(out.replacement[32:], p.index), lib.play_chains(r[32:], p.index))
        forms, plays, links = pk.pack_requests(pack, b.asset_id, b)
        exported = pk.pack_from_staged_rows(team='MIN', book=b, body=r[32:], formation_rows=forms,
                                          play_rows=plays, link_rows=links)
        imported = pk.loads_pack(exported.dumps())
        self.assertEqual({p.custom_name: p.option_intent for p in imported.plays}, {p.custom_name: p.option_intent for p in pack.plays})
        self.assertEqual(imported.schema, pk.OPTION_SCHEMA)
        other = pk.apply_pack_to_resource(r, imported)
        for p in pack.plays:
            self.assertEqual(lib.play_chains(other.replacement[32:], p.replace_index), lib.play_chains(out.replacement[32:], p.replace_index))
        self.assertEqual(len(other.report['option_intent']['records']), 8)
        self.assertEqual(pk.apply_pack_to_resource(r, pack).replacement, out.replacement)
        with self.assertRaisesRegex(pk.PlaybookPackError, 'fingerprint'):
            pk.apply_pack_to_resource(out.replacement, pack)

    def test_foreign_fixture_source_intent_append_and_pool_refuse(self):
        r, b = self.resources['MIN'], self.books['MIN']; pack = pk.load_pack(SEED)
        read = pack.plays[-2]
        bad = deepcopy(read.option_intent); bad['opponent']['signature'] = '0' * 64
        edited = replace(pack, plays=(replace(read, option_intent=bad),))
        with self.assertRaisesRegex(ValidationError, 'signature mismatch'):
            pk.apply_pack_to_resource(r, edited)
        bad = deepcopy(read.option_intent); bad['back_slot'] = 9
        with self.assertRaisesRegex(ValidationError, 'graph'):
            pk.apply_pack_to_resource(r, replace(pack, plays=(replace(read, option_intent=bad),)))
        row = read.request_mapping(b.asset_id); row.pop('replace_index')
        with self.assertRaisesRegex(ValidationError, 'never append'):
            writer.compile_formation_play_creations(r, [], [row])
        # Intent is validated even if every chain is retained from a donor.
        row = read.request_mapping(b.asset_id); row['assignments'] = None
        with self.assertRaisesRegex(ValidationError, 'graph'):
            writer.compile_formation_play_creations(r, [], [row])
        full = bytearray(r); struct.pack_into('<I', full, 32 + 0x40, 3499)
        full[32 + insp.NODE_BASE + 3498 * 8 + 1] = 2
        with self.assertRaisesRegex(ValidationError, 'pool'):
            writer.compile_formation_play_creations(bytes(full), [], [read.request_mapping(b.asset_id)])
        foreign = bytearray(r); foreign[-1] ^= 1
        with self.assertRaisesRegex(pk.PlaybookPackError, 'fingerprint'):
            pk.apply_pack_to_resource(bytes(foreign), pack)
        self.assertEqual(pk.retarget_pack(pack, 'MIN', b, r[32:])[0], pack)
        edited = replace(pack, plays=(replace(pack.plays[0], custom_name='My edited option'), *pack.plays[1:]))
        with self.assertRaisesRegex(pk.PlaybookPackError, 'Regenerate'):
            pk.retarget_pack(edited, 'NO', self.books['NO'], self.resources['NO'][32:])

    def test_gun_defense_option_composition_and_full_270_play_book(self):
        for team in ('MIN', 'CHI', 'ARZ'):
            with self.subTest(team=team):
                r = self.resources[team]
                for name in ('modern_gun_core', 'softdrink_modern_defense'):
                    b = insp.parse_playbook_resource(r)
                    p, _ = pk.retarget_pack(pk.load_pack(ROOT / 'data/playbooks' / (name + '.2k5book')), team, b, r[32:])
                    r = pk.apply_pack_to_resource(r, p).replacement
                b = insp.parse_playbook_resource(r)
                if team == 'MIN':
                    with self.assertRaisesRegex(pk.PlaybookPackError, 'eight replacement calls'):
                        pk.option_pack(b, r[32:], team)
                    continue
                p = pk.option_pack(b, r[32:], team)
                compiled = pk.apply_pack_to_resource(r, p)
                self.assertEqual(compiled.report['new_play_count'], len(b.plays))
                self.assertLessEqual(compiled.report['new_node_count'], 3500)
                self.assertEqual(len(compiled.replacement), 78768)
                # Every call in a gun menu and every defense script survives.
                protected = {l.play_index for f in b.formations
                             if lib.formation_record(r[32:], f.index).qb_alignment == 2 for l in f.play_links}
                protected |= {p.index for p in b.plays if p.family_id == 1}
                for pi in protected:
                    self.assertEqual(lib.play_chains(r[32:], pi), lib.play_chains(compiled.replacement[32:], pi))
                for play in compiled.parsed_replacement.plays:
                    flags, a = lib.play_chains(compiled.replacement[32:], play.index)
                    self.assertIsNone(codec.validate_play(flags, a))
                    codec.validate_sync(a)


if __name__ == '__main__':
    unittest.main()
