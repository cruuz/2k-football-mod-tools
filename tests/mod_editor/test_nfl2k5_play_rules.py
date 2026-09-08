"""Standalone rule extraction, compilation, provenance and reference checks."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tools'):
    sys.path.insert(0, str(path))

from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_play_rules as rules
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_formation_play_writer as writer
from mod_editor.core import nfl2k5_playbook_pack as pk
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_nfl2k5_defense_play import retail_resources, EXTRACT


class RuleReferenceTests(unittest.TestCase):
    def test_all_29_opcodes_and_current_schema_parameters_are_explained(self):
        data = rules.reference()
        self.assertEqual(len(data['opcodes']), 29)
        for row in data['opcodes']:
            op = row['opcode']
            self.assertTrue(row['meaning'])
            self.assertEqual(row['name'], codec.OPCODE_NAMES[op])
            self.assertEqual([s['key'] for s in row['parameters']],
                             [s.key for s in codec.OPERAND_SCHEMAS[op]])
            self.assertEqual(set(row['callbacks']), {'decode', 'encode', 'draw', 'validate'})
        self.assertIn('Rejected', data['opcodes'][25]['meaning'])
        data['opcodes'][0]['meaning'] = 'changed'
        self.assertNotEqual(data['opcodes'][0]['meaning'], rules.reference()['opcodes'][0]['meaning'])

    def test_reference_distinguishes_runtime_and_missing_donors(self):
        data = rules.reference()
        self.assertEqual({r['name'] for r in data['unavailable']},
                         {'Combo Inside Zone: OL rules', 'Inside Zone Read', 'Slide protection'})
        text = json.dumps(data)
        for term in ('31 records', '270', '3,500', 'PRACTICE', 'HYPOTHESIS', 'UNWITNESSED'):
            self.assertIn(term, text)
        for section in data['sections']:
            for path in section.get('links', []):
                self.assertTrue((ROOT / path).is_file(), path)

    def test_friend_namespace_matches_existing_retarget_contract(self):
        examples = [(0x02, [0]), (0x13, [10, 0]), (0x15, [2, 0, 0, 0, 0, 9, 0]),
                    (0x0E, [0, 0, 0, 9, 7, 4, 1, 1]),
                    (0x1A, [6, 0, 0, 10, 4, 0, 3, 0]),
                    (0x1A, [4, 0, 0, 2, 4, 1, 13, 0])]
        for op, vals in examples:
            field, predicate = pk.SLOT_OPERANDS[op]
            expected = field if predicate is None or predicate(vals) else None
            self.assertEqual(rules.friendly_operand(op, vals), expected)


class RetailRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = retail_resources()
        cls.books = {team: insp.parse_playbook_resource(raw, asset_id='book:' + team)
                     for team, raw in cls.resources.items()}

    def test_representative_full_resource_roundtrips_and_every_encoded_byte(self):
        for sample in rules.reference()['samples']:
            with self.subTest(sample=sample['id']):
                raw = self.resources[sample['book']]
                body = raw[32:]
                book = self.books[sample['book']]
                p, f = sample['play'], sample['formation']
                bundle = rules.extract_bundle(book, body, f, p)
                # Independent comparison against the original pointer-resolved bytes.
                expected = lib.play_chains(body, p)[1]
                for slot, chain in enumerate(bundle.chains()):
                    self.assertEqual([n.to_bytes() for n in codec.encode_chain(chain)], expected[slot][1])
                    self.assertTrue(all(len(n) == 3 for n in chain))
                application = rules.apply_bundle(bundle, book, body, f, p)
                compiled = rules.compile_application(raw, book, application, replace_index=p)
                self.assertEqual(compiled.replacement, raw)
                self.assertEqual(compiled.changed_ranges, ())
                self.assertEqual(compiled.changed_byte_count, 0)
                self.assertEqual(compiled.source_sha256, compiled.replacement_sha256)
                self.assertEqual(compiled.report['old_node_count'], compiled.report['new_node_count'])

    def test_combo_is_defense_and_source_pairs_cannot_be_split(self):
        book, body = self.books['ATL'], self.resources['ATL'][32:]
        self.assertEqual(book.plays[28].family_id, 1)
        with self.assertRaisesRegex(ValidationError, 'slot|distinct'):
            rules.extract_bundle(book, body, 23, 28, scope='line')
        with self.assertRaisesRegex(ValidationError, '9'):
            rules.extract_bundle(book, body, 23, 28, slots=(4,))
        bundle = rules.extract_bundle(book, body, 23, 28, slots=(4, 9))
        app = rules.apply_bundle(bundle, book, body, 23, 25)
        self.assertEqual(app.target_slots, (4, 9))
        self.assertEqual(app.chains[4][2][1][5], 9)
        self.assertEqual(app.chains[9][1][1][5], 4)
        for slot in set(range(11)) - {4, 9}:
            self.assertEqual(app.chains[slot], lib.exact_play_chains(body, 25)[slot])

    def test_copied_combo_compiles_into_different_play_and_v3_pack(self):
        raw, book = self.resources['ATL'], self.books['ATL']
        body = raw[32:]
        bundle = rules.extract_bundle(book, body, 23, 28, scope='active')
        app = rules.apply_bundle(bundle, book, body, 23, 25)
        request = writer.rule_play_request(book.asset_id, body, 25, app.chains,
                                          custom_name='Copied exchange', replace_index=25)
        restored = writer.play_request_from_mapping(json.loads(json.dumps(request.provider_edit())))
        compiled = writer.compile_formation_play_creations(raw, play_requests=(restored,))
        new = lib.play_chains(compiled.replacement[32:], 25)[1]
        original = lib.play_chains(body, 28)[1]
        for slot in bundle.slots:
            self.assertEqual(new[slot][1], original[slot][1])
        self.assertEqual(compiled.replacement[:32], raw[:32])
        self.assertEqual(len(compiled.replacement), len(raw))
        self.assertEqual(compiled.report['new_play_count'], len(book.plays))
        self.assertTrue(compiled.report['defense_menus'])
        donor = pk.PackDonor(25, book.plays[25].name, book.plays[25].flags_or_id,
                            lib.defense_signature(body, 25))
        play = pk.PackPlay('copied', 'Copied exchange', 'defense', request.assignments,
                          donor, donor.flags, 25, book.plays[25].name,
                          'Custom copied rules', defense_formation='Nickel', front_index=0,
                          component='coverage')
        pack = pk.PlaybookPack(pk.PackBook('ATL', 'Rules test', 'tester', '1.0', 'CC0-1.0'),
            pk.PackBase(pk.book_fingerprint(body), len(book.formations), len(book.plays), book.node_count),
            (), (play,), pk.OPTION_SCHEMA)
        loaded = pk.loads_pack(pack.dumps())
        self.assertEqual(loaded.dumps(), pack.dumps())
        self.assertTrue(pk.check_pack(loaded, book, body).ok)
        self.assertEqual(pk.apply_pack_to_resource(raw, loaded).replacement, compiled.replacement)

    def test_ol_rules_move_to_another_formation_without_copying_skill_chains(self):
        book, body = self.books['ATL'], self.resources['ATL'][32:]
        bundle = rules.extract_bundle(book, body, 6, 77, scope='line')
        app = rules.apply_bundle(bundle, book, body, 2, 98)
        self.assertEqual(app.target_slots, (1, 2, 3, 4, 5))
        for slot in (0, 6, 7, 8, 9, 10):
            self.assertEqual(app.chains[slot], lib.exact_play_chains(body, 98)[slot])
        compiled = rules.compile_application(self.resources['ATL'], book, app,
                                             replace_index=98, custom_name='Outside line')
        source = lib.play_chains(body, 77)[1]
        target = lib.play_chains(compiled.replacement[32:], 98)[1]
        for slot in range(1, 6):
            self.assertEqual(source[slot][1], target[slot][1])

    def test_slot_remap_changes_friendly_partner_but_not_opponent_or_flags(self):
        book, body = self.books['ATL'], self.resources['ATL'][32:]
        bundle = rules.extract_bundle(book, body, 23, 28)
        codes = list(bundle.position_codes)
        codes[4], codes[6] = codes[6], codes[4]
        app = rules.apply_bundle(bundle, book, body, 23, 28, position_codes=codes)
        self.assertEqual(app.chains[9][1][1][5], 6)  # friendly source slot 4 moved
        self.assertEqual(app.chains[9][1][1][3], bundle.chains()[9][1][1][3])  # opponent
        self.assertEqual(app.chains[6][2][2], bundle.chains()[4][2][2])
        raw = self.resources['MIN']; book = self.books['MIN']; body = raw[32:]
        bundle = rules.extract_bundle(book, body, 12, 24)
        codes = list(bundle.position_codes); codes[9], codes[10] = codes[10], codes[9]
        app = rules.apply_bundle(bundle, book, body, 12, 24, position_codes=codes)
        self.assertEqual(app.chains[9][1][1][6], 3)  # source node, not player slot
        self.assertEqual(app.chains[0][4][1][0], 9)  # pitch partner

    def test_incompatible_source_family_class_personnel_and_target_pair_refuse(self):
        book, body = self.books['ATL'], self.resources['ATL'][32:]
        line = rules.extract_bundle(book, body, 6, 77, scope='line')
        for f, p in ((23, 25), (12, 60)):
            with self.assertRaises(ValidationError):
                rules.apply_bundle(line, book, body, f, p)
        bad_codes = [0] * 11
        with self.assertRaisesRegex(ValidationError, 'formation has'):
            rules.apply_bundle(line, book, body, 6, 77, position_codes=bad_codes)
        with self.assertRaisesRegex(ValidationError, 'currently loaded'):
            rules.apply_bundle(replace(line, source_body_sha256='0'*64), book, body, 6, 77)
        application = rules.apply_bundle(line, book, body, 6, 77)
        changed = bytearray(self.resources['ATL']); changed[-1] ^= 1
        with self.assertRaisesRegex(ValidationError, 'before compilation'):
            rules.compile_application(bytes(changed), book, application, replace_index=77)
        with self.assertRaisesRegex(ValidationError, 'source formation'):
            rules.extract_bundle(book, body, 23, 77)
        solo = rules.extract_bundle(book, body, 23, 25, slots=(4,))
        with self.assertRaisesRegex(ValidationError, 'existing linked'):
            rules.apply_bundle(solo, book, body, 23, 28)
        for slots in ((), (4, 4), (-1,), (11,), (True,)):
            with self.assertRaises(ValidationError):
                rules.extract_bundle(book, body, 23, 25, slots=slots)

    def test_viewer_includes_both_option_terminals_and_every_raw_node(self):
        raw, book = self.resources['MIN'], self.books['MIN']
        doc = rules.inspect_play(book, raw[32:], 24, 12)
        self.assertEqual(len(doc['assignments']), 11)
        for slot in (0, 10):
            nodes = doc['assignments'][slot]['nodes']
            self.assertEqual(len(nodes), 5)
            self.assertEqual(sum(bool(int(n['flags'], 16) & 2) for n in nodes), 2)
            self.assertTrue(any(n['condition'] is not None for n in nodes))
        changed = bytearray(raw[32:]); changed[insp.PLAY_BASE + 24*96 + 4] ^= 1
        with self.assertRaisesRegex(ValidationError, 'do not match'):
            rules.inspect_play(book, bytes(changed), 24)

    def test_named_catalog_has_real_linked_donors_across_all_books(self):
        found = set()
        for team, book in self.books.items():
            body = self.resources[team][32:]
            for row in rules.catalog(book, body):
                found.add(row['preset'])
                bundle = rules.extract_bundle(book, body, row['formation'], row['play'], scope=row['scope'])
                self.assertTrue(bundle.slots)
                self.assertEqual(bundle.source_body_sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(found, {p['id'] for p in rules.reference()['presets']})

    def test_capacity_and_foreign_encoded_bytes_refuse_without_mutation(self):
        raw, book = self.resources['ATL'], self.books['ATL']
        body = raw[32:]
        req = writer.PlayCreateRequest(book.asset_id, 25, 'Too many',
                pk._freeze_chains(lib.exact_play_chains(body, 28)), replace_index=25)
        count = (writer.NODE_CAPACITY - book.node_count) // 26 + 1
        with self.assertRaisesRegex(ValidationError, 'node pool is full'):
            writer.compile_formation_play_creations(raw, play_requests=(req,) * count)
        bad = bytearray(body)
        start = book.plays[25].assignments[4].chain_start_index
        bad[insp.NODE_BASE + start*8 + 2] = 1
        with self.assertRaisesRegex(ValueError, 'cannot preserve'):
            lib.exact_play_chains(bytes(bad), 25)
        self.assertEqual(self.resources['ATL'], raw)


if __name__ == '__main__':
    unittest.main()
