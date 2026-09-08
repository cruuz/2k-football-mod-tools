"""Standalone census, exact native compilation and pack composition acceptance."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tools'):
    sys.path.insert(0, str(path))

from mod_editor.core import nfl2k5_match_coverage as match
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_play_rules as rules
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_playbook_pack as pk
from mod_editor.core.errors import ValidationError

EXTRACT = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')
ART = ROOT / 'docs/mod_editor/match_coverage'
SEED = ROOT / 'data/playbooks/softdrink_match_coverage.2k5book'


def resources():
    if not (EXTRACT / 'vc_53450030/0').is_file():
        raise unittest.SkipTest('Retail extracted vc_53450030/0 is absent; exact PLAY acceptance requires it')
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    with OuterImage(EXTRACT) as archive:
        return {team: archive.read_entry(entry) for team, entry in BOOK_ENTRIES.items()}


class MatchPortableTests(unittest.TestCase):
    def test_ordinary_man_flag_and_spot_zones_are_not_matches(self):
        chain = [(0x1B, [0, 0, 0, 0, 17, 0]), (0x0E, [0, 100, 0, 0, 0, 0, 0, 1])]
        a = match.analyze_chains([chain] * 11)
        self.assertEqual(a['rules'], [])
        self.assertEqual(a['unresolved'], [])
        zone = [(0x1B, [0, 0, 0, 0, 17, 0]), (0x0D, [0, 1500, 0, 0, 8, 0, 0])]
        self.assertFalse(match.analyze_chains([zone] * 11)['rules'])

    def test_unknown_predicate_and_unarmed_continuation_stay_visible(self):
        chain = [(0x1B, [0, 0, 0, 0, 17, 0]), (0x1A, [4, 0, 0, 0, 0, 0, 0, 0]),
                 (0x0E, [0, 100, 0, 0, 0, 0, 0, 0])]
        a = match.analyze_chains([chain] * 11)
        self.assertEqual(len(a['predicates']), 11)
        self.assertEqual(len(a['unresolved']), 11)
        chain[1] = (0x0D, [0, 800, 0, 0, 4, 0, 0])
        self.assertFalse(match.analyze_chains([chain] * 11)['rules'])
        with self.assertRaises(ValidationError):
            match.analyze_chains([chain])

    def test_boundaries_distinguish_lateral_from_depth(self):
        self.assertIn('15 yards', match.boundary_words(7))
        self.assertNotIn('left', match.boundary_words(7))
        self.assertIn('left', match.boundary_words(13))
        self.assertNotIn('15 yards', match.boundary_words(13))
        self.assertIn('right', match.boundary_words(14))
        with self.assertRaises(ValidationError):
            match.boundary_words(16)

    def test_pack_is_portable_and_discloses_modern_policy_limits(self):
        pack = pk.load_pack(SEED)
        self.assertEqual(pack.schema, pk.DEFENSE_SCHEMA)
        self.assertEqual(pk.loads_pack(pack.dumps()), pack)
        self.assertEqual([p.custom_name for p in pack.plays], list(match.PACK_NAMES))
        self.assertTrue(pk.check_pack(pack).ok)
        self.assertEqual(sum(p.node_count for p in pack.plays), 122)
        for words in ('UNWITNESSED', '#2', 'Palms', 'Rip', 'Liz', 'robber'):
            self.assertIn(words, pack.book.notes)
        self.assertFalse(any(p.spy_slots or p.option_intent for p in pack.plays))

    def test_census_gallery_is_complete_with_pinned_pngs(self):
        doc = json.loads((ART / 'census.json').read_text())
        self.assertEqual(doc['totals']['matched_plays'], 59)
        self.assertEqual(doc['totals']['matched_menu_entries'], 105)
        self.assertEqual(doc['totals']['reciprocal_plays'], 53)
        self.assertEqual(doc['totals']['unclassified_plays'], 0)
        images = [f['image'] for b in doc['books'] for p in b['matches'] for f in p['formations']]
        self.assertEqual(len({i['file'] for i in images}), 105)
        images.extend(json.loads((ART / 'pack_receipt.json').read_text())['images'])
        self.assertEqual({p.name for p in ART.glob('*.png')}, {i['file'] for i in images})
        for i in images:
            raw = (ART / i['file']).read_bytes()
            self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', raw[16:24]), (1280, 940))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), i['sha256'], i['file'])


class MatchRetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources = resources()  # 37 x 78 KB, never a disc or pack in RAM
        cls.books = {t: insp.parse_playbook_resource(r, asset_id='book:' + t) for t, r in cls.resources.items()}
        cls.seed = pk.load_pack(SEED)

    def test_full_census_reproduces_every_book_and_detects_six_native_anomalies(self):
        expected = json.loads((ART / 'census.json').read_text())
        found = []
        for b in expected['books']:
            for p in b['matches']:
                for f in p['formations']:
                    f.pop('image')
            actual = match.census_book(self.resources[b['book']], b['book'])
            self.assertEqual(actual, b, b['book'])
            if actual['unresolved']:
                found.append(b['book'])
        self.assertEqual(found, ['CHI', 'CIN', 'JAX', 'KC', 'TEN', 'WAS'])
        self.assertEqual(expected['totals']['plays'], 9251)
        self.assertEqual(expected['totals']['defensive_plays'], 3332)
        self.assertEqual(expected['totals']['nodes'], 91833)
        self.assertEqual(expected['totals']['predicate_nodes'], 0)

    def test_ravens_vertical_handoff_and_renamed_rule_bundle(self):
        b, raw = self.books['BAL'], self.resources['BAL']
        chains = lib.exact_play_chains(raw[32:], 14)
        a = match.analyze_chains(chains)
        self.assertEqual([(p['man_slot'], p['zone_slot'], p['boundary']) for p in a['pairs']],
                         [(9, 7, 7), (10, 8, 7)])
        self.assertFalse(a['unresolved'])
        bundle = rules.extract_bundle(b, raw[32:], 25, 14)
        result = rules.compile_application(raw, b, rules.apply_bundle(bundle, b, raw[32:], 25, 14), replace_index=14)
        self.assertEqual(result.replacement, raw)
        renamed = replace(b, plays=tuple(replace(p, name='No match keywords') if p.index == 14 else p for p in b.plays))
        rows = match.rule_catalog(renamed, raw[32:])
        self.assertTrue(any(r['play'] == 14 and r['label'] == 'Match: vertical handoff' for r in rows))
        with self.assertRaisesRegex(ValidationError, 'linked'):
            rules.extract_bundle(b, raw[32:], 25, 14, slots=(9,))

    def test_all_37_compile_without_touching_stock_rules_or_personnel(self):
        for team, raw in self.resources.items():
            with self.subTest(team=team):
                book = self.books[team]
                pack, _ = pk.retarget_pack(self.seed, team, book, raw[32:])
                compiled = pk.apply_pack_to_resource(raw, pack)
                out, new = compiled.replacement, compiled.parsed_replacement
                self.assertEqual(len(out), 78768)
                self.assertEqual(out[:32], raw[:32])
                self.assertEqual(out[32 + insp.CATEGORY_BASE:32 + insp.NODE_BASE],
                                 raw[32 + insp.CATEGORY_BASE:32 + insp.NODE_BASE])
                self.assertEqual(new.node_count - book.node_count, 122)
                replaced = {p.replace_index for p in pack.plays}
                for p in book.plays:
                    if p.index not in replaced:
                        self.assertEqual(lib.play_chains(raw[32:], p.index), lib.play_chains(out[32:], p.index))
                if team not in ('Editor', 'PRACTICE'):
                    self.assertEqual(new.formations, book.formations)
                    self.assertEqual(len(new.plays), len(book.plays))
                else:
                    self.assertEqual(len(new.plays), len(book.plays) + 5)
                for p in new.plays:
                    self.assertIsNone(codec.validate_play(*lib.play_chains(out[32:], p.index)))
                for menu in compiled.report['defense_menus']:
                    self.assertTrue(menu['pairs'])
                    self.assertTrue(all(pair['active'] == list(range(11)) for pair in menu['pairs']))
                for i, p in enumerate(pack.plays):
                    analysis = match.analyze_chains(p.assignments)
                    self.assertEqual(len(analysis['pairs']), (1, 1, 2, 2, 0)[i])
                    self.assertFalse(analysis['unresolved'])
                    if i == 4:
                        effective = lib.effective_defense(lib.decoded_chains(out[32:], p.front_index), p.assignments)
                        counts = lib.defense_counts(effective)
                        self.assertEqual((len(counts['rushers']), len(counts['deep'])), (4, 1))
                        self.assertEqual(sum(any(n[0] == 0x0E for n in c) for c in effective), 5)

    def test_all_37_defense_pack_orders_and_32_gun_compositions(self):
        modern_seed = pk.load_pack(ROOT / 'data/playbooks/softdrink_modern_defense.2k5book')
        gun_seed = pk.load_pack(ROOT / 'data/playbooks/modern_gun_core.2k5book')
        receipts = []
        for team, retail in self.resources.items():
            for order in ((modern_seed, self.seed), (self.seed, modern_seed)):
                with self.subTest(team=team, first=order[0].book.name):
                    raw, book = retail, self.books[team]
                    sequence = order
                    if team in pk.TEAM_BOOKS:
                        # Cover both gun-first retargeting and Build's actual
                        # defense-before-offense ordering across all 32 teams.
                        sequence = (gun_seed, *order) if order[0] is modern_seed else (*order, gun_seed)
                    for seed in sequence:
                        pack, _ = pk.retarget_pack(seed, team, book, raw[32:])
                        c = pk.apply_pack_to_resource(raw, pack)
                        raw, book = c.replacement, c.parsed_replacement
                    self.assertTrue(set(match.PACK_NAMES + match.MODERN_NAMES) <= {p.name for p in book.plays})
                    self.assertLessEqual(book.node_count, 3500)
                    if team == 'CHI':
                        self.assertEqual(book.node_count, 3389)
                    receipts.append(dict(book=team, order=[p.book.name for p in sequence],
                        source_sha256=hashlib.sha256(retail).hexdigest(),
                        replacement_sha256=hashlib.sha256(raw).hexdigest(), nodes=book.node_count,
                        spare_nodes=3500 - book.node_count, plays=len(book.plays)))
        if os.environ.get('NFL2K5_MATCH_ACCEPTANCE_OUTPUT'):
            Path(os.environ['NFL2K5_MATCH_ACCEPTANCE_OUTPUT']).resolve().write_text(
                json.dumps(dict(schema='nfl2k5_match_pack_composition/v1', results=receipts), indent=2) + '\n')

    def test_changed_sources_custom_edits_and_incomplete_recipes_refuse(self):
        raw, b = self.resources['BAL'], self.books['BAL']
        dirty = bytearray(raw); dirty[32 + insp.NODE_BASE + 4] ^= 1
        with self.assertRaises(ValidationError):
            pk.apply_pack_to_resource(bytes(dirty), self.seed)
        doc = self.seed.to_json()
        doc['plays'][0]['assignments'][9][1][1][5] = 6
        altered = pk.pack_from_json(doc)
        self.assertFalse(pk.check_pack(altered, resource=raw).ok)
        partial = replace(self.seed, plays=self.seed.plays[:-1])
        with self.assertRaisesRegex(ValidationError, 'all five'):
            pk.retarget_pack(partial, 'BAL', b, raw[32:])
        completed = pk.apply_pack_to_resource(raw, self.seed)
        with self.assertRaisesRegex(ValidationError, 'already contains'):
            match.match_coverage_pack(completed.parsed_replacement, completed.replacement[32:], 'BAL')

    def test_archive_preflight_has_no_writes_when_a_later_book_is_full(self):
        payloads = [self.resources['BAL'], bytearray(self.resources['CHI'])]
        struct.pack_into('<I', payloads[1], 32 + 0x40, 3490)
        payloads[1] = bytes(payloads[1])
        class Archive:
            entries = [SimpleNamespace(size=78768, virtual_offset=i * 78768) for i in range(2)]
            writes = []
            def read_entry(self, index):
                return payloads[index]
            def write(self, offset, payload):
                self.writes.append((offset, len(payload)))
                return len(payload)
        archive = Archive()
        pack = replace(self.seed, book=replace(self.seed.book, targets=('BAL', 'CHI')))
        with self.assertRaises(ValidationError):
            pk.apply_packs_to_archive(archive, [('match', pack)], book_entries={'BAL': 0, 'CHI': 1})
        self.assertEqual(archive.writes, [])


if __name__ == '__main__':
    unittest.main()
