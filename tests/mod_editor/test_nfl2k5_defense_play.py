"""Defense authoring acceptance: native bytes, all 37 books, portable intent.

Plain standalone unittest. Retail tests skip precisely when the extracted
archive is absent; numeric-domain and schema tests require no private files.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / 'tools'):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_playbook_pack as pk
from mod_editor.core import nfl2k5_formation_play_writer as writer
from mod_editor.core.errors import ValidationError

EXTRACT = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')
SEED = ROOT / 'data/playbooks/softdrink_modern_defense.2k5book'


def retail_resources():
    if not (EXTRACT / 'vc_53450030/0').is_file():
        raise unittest.SkipTest('retail extracted vc_53450030/0 missing')
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    with OuterImage(EXTRACT) as archive:
        return {team: archive.read_entry(BOOK_ENTRIES[team]) for team in pk.DEFENSE_BOOKS}


class DefenseOfflineTests(unittest.TestCase):
    def test_correct_native_names_and_seventeen_lanes(self):
        self.assertEqual([codec.position_label(c) for c in (14, 15, 16, 17, 18, 0x52, 0x72)],
                         ['MLB', 'OLB', 'FS', 'SS', 'CB', 'CB3', 'CB4'])
        self.assertEqual(len(codec.LANE_TABLE_CM), 17)
        self.assertAlmostEqual(codec.LANE_TABLE_CM[16], 685.8)
        art = codec.play_art([codec.Node(0x0B, 6, [3, 16, 0])], (0, 0))
        self.assertAlmostEqual(art[0].points[-1][0], 685.8)

    def test_domains_refuse_wrap_nonfinite_illegal_ops_and_foreign_slots(self):
        legal = [(0x1B, [0, 0, 0, 0, 17, 0]), (0x0D, [0, 4 * lib.YD, 8, 7, 4, 0, 0])]
        codec.validate_defense_operands(legal)
        for opcode in (0x09, 0x0A, 0x0C, 0x10, 0x1A):
            with self.assertRaises(ValueError):
                codec.validate_defense_operands([(opcode, [0] * len(codec.OPERAND_SCHEMAS[opcode]))])
        for value in (128 * codec.FT_CM, -129 * codec.FT_CM, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                codec.validate_defense_operands([(0x0D, [value, 0, 0, 0, 4, 0, 0])])
        for lane in (-1, 18, 32):
            with self.assertRaises(ValueError):
                codec.validate_defense_operands([(0x0B, [2, lane, 0])])
        with self.assertRaises(ValueError):
            codec.validate_defense_operands([(0x0E, [0, 0, 0, 8, 4, 11, 1, 1])])

    def test_friendly_exchange_partner_moves_but_opponent_does_not(self):
        chains = [[(0x0E, [0, 0, 0, 9, 7, 9, 1, 1])] for _ in range(11)]
        order = list(range(11)); order[4], order[9] = order[9], order[4]
        moved = pk.permute_assignments(chains, order)
        self.assertEqual(moved[9][0][1][3], 9)  # opponent
        self.assertEqual(moved[9][0][1][5], 4)  # teammate
        chains[4][0][1][7] = 0  # retail man-to-zone partner has e=0, transition=1
        moved = pk.permute_assignments(chains, order)
        self.assertEqual(moved[9][0][1][5], 4)
        with self.assertRaises(pk.PlaybookPackError):
            pk.permute_assignments(chains, [0] * 11)

    def test_versioned_pack_and_intent_reject_legacy_or_unknown(self):
        pack = pk.load_pack(SEED)
        self.assertEqual(pack.schema, pk.DEFENSE_SCHEMA)
        self.assertEqual(pk.loads_pack(pack.dumps()).dumps(), pack.dumps())
        self.assertTrue(pk.check_pack(pack).ok)
        doc = pack.to_json(); doc['schema'] = pk.SCHEMA
        with self.assertRaisesRegex(pk.PlaybookPackError, 'schema v2'):
            pk.pack_from_json(doc)
        with self.assertRaisesRegex(ValidationError, 'schema'):
            writer.spy_slots_from({'schema': 'nfl2k5_spy_intent/v2', 'slots': [5]})
        with self.assertRaisesRegex(ValidationError, 'duplicate'):
            writer.spy_slots_from({'schema': lib.SPY_INTENT_SCHEMA, 'slots': [5, 5]})

    def test_smallest_retail_budget_and_cumulative_overflow(self):
        pack = pk.load_pack(SEED)
        # CHI 2739, gun +308, defense +220: 3267 of 3500.
        pack = replace(pack, base=replace(pack.base, donor_node_count=2739 + 308))
        self.assertEqual(pk.budget_totals(pack)['nodes'], 3267)
        self.assertTrue(pk.check_pack(pack).ok)
        over = replace(pack, base=replace(pack.base, donor_node_count=3500 - 219))
        self.assertFalse(pk.check_pack(over).ok)


class DefenseRetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = retail_resources()
        cls.books = {team: insp.parse_playbook_resource(r, asset_id='book:' + team) for team, r in cls.resources.items()}

    def test_every_retail_play_and_defense_node_round_trips(self):
        count = defense = 0
        for team, r in self.resources.items():
            b = self.books[team]
            for play in b.plays:
                flags, assignments = lib.play_chains(r[32:], play.index)
                self.assertIsNone(codec.validate_play(flags, assignments), (team, play.index))
                count += 1
                if play.family_id != 1:
                    continue
                defense += 1
                for slot, (descriptor, nodes) in enumerate(assignments):
                    self.assertEqual(codec.build_descriptor(flags, assignments, slot, descriptor >> 24), descriptor)
                    for node in nodes:
                        self.assertEqual(codec.Node.from_bytes(node).to_bytes(), node)
        self.assertEqual((count, defense), (9251, 3332))

    def test_all_37_compile_category_isolation_pairing_and_real_gun_composition(self):
        seed = pk.load_pack(SEED)
        gun = pk.load_pack(ROOT / 'data/playbooks/modern_gun_core.2k5book')
        for team, r in self.resources.items():
            with self.subTest(team=team):
                book = self.books[team]
                pack, _ = pk.retarget_pack(seed, team, book, r[32:])
                check = pk.check_pack(pack, resource=r)
                self.assertTrue(check.ok, check.errors)
                compiled = pk.apply_pack_to_resource(r, pack)
                out = compiled.replacement
                for play in compiled.parsed_replacement.plays:
                    flags, assignments = lib.play_chains(out[32:], play.index)
                    self.assertIsNone(codec.validate_play(flags, assignments), (team, play.index))
                self.assertEqual(len(out), 78768)
                self.assertEqual(out[:32], r[:32])
                # Exact rows, including names, code and personnel; no shared row writes.
                self.assertEqual(out[32 + insp.CATEGORY_BASE:32 + insp.NODE_BASE],
                                 r[32 + insp.CATEGORY_BASE:32 + insp.NODE_BASE])
                self.assertEqual(compiled.report['new_node_count'] - book.node_count, 220)
                for fi in range(len(book.formations)):
                    start = 32 + insp.FORMATION_BASE + fi * insp.FORMATION_SIZE
                    self.assertEqual(out[start:start + insp.FORMATION_SIZE], r[start:start + insp.FORMATION_SIZE])
                if team not in ('Editor', 'PRACTICE'):
                    self.assertEqual(len(compiled.parsed_replacement.plays), len(book.plays))
                    self.assertEqual(compiled.parsed_replacement.formations, book.formations)
                for row in compiled.report['defense_menus']:
                    self.assertTrue(row['pairs'])
                    for pair in row['pairs']:
                        self.assertEqual(pair['active'], list(range(11)))
                for play in pack.plays:
                    counts = lib.defense_counts(lib.effective_defense(lib.decoded_chains(out[32:], play.front_index),
                        lib.decoded_chains(out[32:], play.replace_index if play.replace_index is not None else len(book.plays) + pack.plays.index(play))))
                    expected = [(6, 0), (5, 1), (4, 2), (4, 2), (4, 2), (4, 3), (4, 4), (4, 3), (5, 3), (4, 3)][pack.plays.index(play)]
                    self.assertEqual((len(counts['rushers']), len(counts['deep'])), expected)
                if team in pk.TEAM_BOOKS:
                    g, _ = pk.retarget_pack(gun, team, book, r[32:])
                    gun_result = pk.apply_pack_to_resource(r, g)
                    composed_book = gun_result.parsed_replacement
                    d, _ = pk.retarget_pack(seed, team, composed_book, gun_result.replacement[32:])
                    composed = pk.apply_pack_to_resource(gun_result.replacement, d)
                    self.assertLessEqual(composed.report['new_node_count'], 3500)

    def test_multi_book_preflight_refuses_smallest_budget_before_any_write(self):
        from types import SimpleNamespace
        resources = [self.resources['ATL'], self.resources['CHI']]
        # A structurally parseable book with insufficient unallocated tail.
        full = bytearray(resources[1]); struct.pack_into('<I', full, 32 + 0x40, 3499)
        resources[1] = bytes(full)
        class Archive:
            entries = [SimpleNamespace(size=78768, virtual_offset=i * 78768) for i in range(2)]
            writes = []
            def read_entry(self, index):
                return resources[index]
            def write(self, offset, payload):
                self.writes.append(offset)
                return len(payload)
        archive = Archive()
        pack = pk.load_pack(SEED)
        pack = replace(pack, book=replace(pack.book, targets=('ATL', 'CHI')))
        with self.assertRaises(ValidationError):
            pk.apply_packs_to_archive(archive, [('defense', pack)], book_entries={'ATL': 0, 'CHI': 1})
        self.assertEqual(archive.writes, [])

    def test_native_personnel_namespace_and_shared_row_refusal(self):
        b, body = self.books['ATL'], self.resources['ATL'][32:]
        info = lib.defense_personnel(b, body, 23)
        self.assertEqual((info['category_index'], info['category_code']), (11, 14))
        self.assertEqual(info['codes'][5] & 31, lib.MLB)
        bal = lib.defense_personnel(self.books['BAL'], self.resources['BAL'][32:], 26)
        cle = lib.defense_personnel(self.books['CLE'], self.resources['CLE'][32:], 28)
        self.assertEqual(bal['codes'][0] & 31, lib.OLB)
        self.assertEqual(cle['codes'][5] & 31, lib.OLB)
        codes = list(info['codes']); codes[5] = lib.CB
        with self.assertRaisesRegex(ValidationError, 'shared category'):
            writer.compile_formation_play_creations(self.resources['ATL'], [writer.FormationCreateRequest(
                'book:ATL', 23, category_index=11, category_positions=tuple(codes))])
        recoded = bytearray(body); recoded[insp.CATEGORY_BASE + 11 * 16 + 5] = 7
        with self.assertRaisesRegex(ValueError, 'recoded'):
            lib.defense_personnel(b, bytes(recoded), 23)
        from nfl2k5_playbook_position_recode import recode_codes
        pooled, _ = recode_codes(info['codes'], 5)
        recoded = bytearray(body)
        off = insp.CATEGORY_BASE + 11 * 16 + 5
        recoded[off:off + 11] = bytes(pooled)
        with self.assertRaisesRegex(ValueError, 'fingerprint|recoded'):
            lib.defense_personnel(b, bytes(recoded), 23)

    def test_double_a_three_columns_package_eligibles_and_mirrors(self):
        r = self.resources['ATL']; b = self.books['ATL']
        positions = lib.double_a_positions(b, r[32:], 23)
        compiled = writer.compile_formation_play_creations(r, [writer.FormationCreateRequest(
            'book:ATL', 23, 'Double A EXPERIMENTAL', tuple(positions), 11)])
        fi = compiled.new_formation_indices[0]
        rec = lib.formation_record(compiled.replacement[32:], fi)
        original = lib.formation_record(r[32:], 23)
        self.assertEqual(rec.package_map, original.package_map)
        self.assertEqual(rec.eligible, b'\xff' * 5)
        self.assertEqual([s.mirror_partner for s in rec.slots], [s.mirror_partner for s in original.slots])
        for s, (x, z) in enumerate(positions):
            self.assertEqual(rec.slots[s].x, [x] * 3)
            self.assertEqual(rec.slots[s].z, [z] * 3)
            partner = rec.slots[s].mirror_partner
            if partner < 11:
                self.assertEqual(rec.slots[partner].mirror_partner, s)
        self.assertEqual(positions[4:6], [(-76, 91), (76, 91)])

    def test_spy_preserves_donor_operands_and_metadata_through_clone_mirror_pack_reload(self):
        r = self.resources['ATL']; b = self.books['ATL']; body = r[32:]
        donor, fallback = lib.spy_fallback(b, body, 23, 5, 4)
        flags, original = lib.play_chains(body, donor)
        raw = [codec.Node(op, 0, list(v)) for op, v in fallback]; codec.assign_node_flags(raw)
        self.assertEqual(raw[0].to_bytes(), original[5][1][0])
        self.assertEqual(raw[1].to_bytes()[:6], original[5][1][1][:6])
        self.assertEqual(raw[1].to_bytes()[6:], bytes([76, 128]))
        design = lib.make_defense_design(b, body, 23)
        design.set_assignment(b, body, 5, 'spy', depth_yd=4)
        mirrored = lib.mirror_defense_design(lib.mirror_defense_design(design))
        self.assertEqual(mirrored.spy_slots, {5})
        self.assertEqual(pk._freeze_chains(mirrored.chains), pk._freeze_chains(design.chains))
        req = writer.PlayCreateRequest('book:ATL', donor, 'SD Spy Interim',
            tuple(tuple((op, tuple(v)) for op, v in fallback) if s == 5 else None for s in range(11)), spy_slots=(5,))
        link = writer.FormationLinkRequest('book:ATL', 23, len(b.plays), 3)
        self.assertEqual(writer.play_request_from_mapping(req.provider_edit()), req)
        compiled = writer.compile_formation_play_creations(r, play_requests=[req], link_requests=[link])
        self.assertEqual(lib.play_chains(compiled.replacement[32:], len(b.plays))[1][5][0], original[5][0])
        lookup = compiled.report['spy_intent']
        self.assertEqual(lookup['schema'], lib.SPY_INTENT_SCHEMA)
        self.assertEqual((lookup['records'][0]['play_index'], lookup['records'][0]['slot']), (254, 5))
        pack = pk.pack_from_staged_rows(team='ATL', book=b, body=body, play_rows=[req.provider_edit()], link_rows=[link.provider_edit()])
        with tempfile.TemporaryDirectory() as td:
            path = pk.save_pack(pack, Path(td).resolve() / 'spy.2k5book')
            loaded = pk.load_pack(path)
            self.assertEqual(loaded.plays[0].spy_slots, (5,))
            self.assertEqual(pk.apply_pack_to_resource(r, loaded).replacement, compiled.replacement)
        with self.assertRaisesRegex(ValueError, 'MLB'):
            lib.spy_fallback(self.books['CLE'], self.resources['CLE'][32:], 28, 5)
        with self.assertRaisesRegex(ValueError, '3 through 5'):
            lib.spy_fallback(b, body, 23, 5, 6)

    def test_foreign_fingerprint_header_and_spy_operands_refused(self):
        r = self.resources['ATL']; b = self.books['ATL']; pack = pk.modern_defense_pack(b, r[32:], 'ATL')
        foreign = bytearray(r); foreign[-1] = 1
        with self.assertRaisesRegex(pk.PlaybookPackError, 'fingerprint'):
            pk.apply_pack_to_resource(bytes(foreign), pack)
        bad = replace(pack.plays[0], donor=replace(pack.plays[0].donor, signature='defense/v1:foreign'))
        with self.assertRaisesRegex(pk.PlaybookPackError, 'signature'):
            pk.apply_pack_to_resource(r, replace(pack, plays=(bad,)))
        donor, chain = lib.spy_fallback(b, r[32:], 23, 5)
        chain[0][1][2] = 30.48  # cannot silently change a start operand under Spy intent
        req = writer.PlayCreateRequest('book:ATL', donor, 'Forged Spy',
            tuple(tuple((op, tuple(v)) for op, v in chain) if s == 5 else None for s in range(11)), spy_slots=(5,))
        with self.assertRaisesRegex(ValidationError, 'preserve'):
            writer.compile_formation_play_creations(r, play_requests=[req],
                link_requests=[writer.FormationLinkRequest('book:ATL', 23, len(b.plays), 3)])


if __name__ == '__main__':
    unittest.main()
