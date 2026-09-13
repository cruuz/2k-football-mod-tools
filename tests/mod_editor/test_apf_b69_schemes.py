"""Real scheme writers and model on authored inputs; no retail fixture."""
from pathlib import Path
import csv
import io
import struct
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_offensive_schemes as schemes
from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core import apf2k8_team_tendency as tendency
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core import apf2k8_book_clone as clone
from mod_editor.apf_studio import playcalling_service as service
from tests.mod_editor.test_apf_book_unlock import book_body, roster_body, archive_fixture
from tests.mod_editor.test_apf_formation_alignment_writer import _synthetic_master
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture


def fixture():
    master = bytearray(_synthetic_master(formation_count=163, category_count=28))
    pool = 0x29000
    def name(at, text):
        nonlocal pool
        encoded = (text + '\0').encode('utf-16-be')
        struct.pack_into('>i', master, at, pool - at + 1)
        master[pool:pool+len(encoded)] = encoded
        pool += len(encoded)
    for i in range(28):
        name(0x44+i*16, '5-2:Big' if i == 27 else f'Package {i}')
        master[0x48+i*16] = splb.PERSONNEL_ROWS[i]
        master[0x49+i*16:0x54+i*16] = bytes((0,5,5,6,7,7,10,8,9,9,9))
    for i in range(6):
        name(0x80C4+i*100, f'Authored play {i}')
        struct.pack_into('>II', master, 0x80C8+i*100, 0, 2 if i % 2 else 8)
    b = bytearray(book_body('O-ManBlock'))
    struct.pack_into('>II', b, 0x118, 3<<17 | 0x9200, 1<<3)
    b = splb._compact_normalize(bytes(b))
    rost = bytearray(roster_body())
    tables, _ = tendency.apf_roster.parse_root(rost)
    for i in range(tables[4].count):
        at = tables[4].offset + i*384 + 0xF8
        target = tables[9].offset + i*180
        struct.pack_into('>i', rost, at, target-at+1)
        rost[target+0x5A] = 50
    return b, bytes(master), bytes(rost)


class SchemeTests(unittest.TestCase):
    def test_eight_schemes_write_only_owned_ratings_and_team_fields(self):
        book, master, rost = fixture()
        self.assertEqual(len(schemes.SCHEMES), 8)
        outputs = set()
        for scheme in schemes.SCHEMES:
            edited, changed, receipt = schemes.apply_scheme(book, master, rost, 0, scheme.id)
            outputs.add((edited, changed))
            self.assertEqual(tendency.team_tendency(changed, 0), scheme.run_percentage)
            self.assertEqual(tendency.row_weights(changed, 0), (scheme.run_row_deltas, scheme.pass_row_deltas))
            self.assertEqual(tendency.team_tendency(changed, 1), 50)
            a, b = splb.parse_book(book, 0), splb.parse_book(edited, 0)
            self.assertEqual(a.records[0].entries, b.records[0].entries)
            self.assertEqual(a.records[0].category_index, b.records[0].category_index)
            self.assertEqual(a.records[0].trailer[4:], b.records[0].trailer[4:])
            self.assertEqual(book[0x120:], edited[0x120:])
            self.assertEqual(receipt['available_personnel'], ['11'])
            self.assertTrue(receipt['notes'])
        self.assertEqual(len(outputs), 8)

    def test_shared_tendency_pointer_refused_and_rows_saturate(self):
        book, master, rost = fixture()
        at = tendency._record(rost, 0)
        b = bytearray(rost)
        tables, _ = tendency.apf_roster.parse_root(b)
        field = tables[4].offset + 384 + 0xF8
        struct.pack_into('>i', b, field, at-field+1)
        with self.assertRaisesRegex(ValueError, 'shared'):
            schemes.apply_scheme(book, master, bytes(b), 0, 'wide_zone')
        rost = tendency.set_row_weights(rost, 0, (250,)*11, (250,)*11)
        _, out, _ = schemes.apply_scheme(book, master, rost, 0, 'wide_zone')
        self.assertEqual(tendency.row_weights(out, 0), ((255,)*11, (255,)*11))

    def test_csv_buckets_use_model_and_distinguish_intent_from_result(self):
        book, master, _ = fixture()
        data = schemes.spreadsheet(book, master, 42, team_name='=UNTRUSTED()', scheme_id='air_coryell')
        rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 23)
        self.assertEqual([r['Bucket'] for r in rows], [b.name for b in schemes.BUCKETS])
        for row, bucket in zip(rows, schemes.BUCKETS):
            self.assertEqual(int(row['Engine row (proxy)']), model.requested_offense_row(bucket.situation()))
            self.assertTrue(row['Team'].startswith("'="))
            self.assertIn('UNWITNESSED', row['Limits'])
        self.assertIn('Proxy only', rows[17]['Limits'])
        self.assertEqual({r['Engine row (proxy)'] for r in rows[12:16]}, {'4'})


class SchemeSessionTests(FacadeFixture):
    def setUp(self):
        super().setUp()
        book, master, rost = fixture()
        self.backend.splb = splb
        self.backend.model = model
        self.backend.tendency = tendency
        self.backend.clone = clone
        index = archive_fixture(self.root/'game')
        self.facade.source = self.facade.session.source = type(self.facade.source)(index.parent, index.parent, index, 'd'*64, 0, 'e'*64, 'Synthetic')
        self.backend.initial = service.State(
            {'O-ManBlock': book}, master, rost,
            tuple({'team_index': i, 'team_name': f'Synthetic Team {i}', 'offense': 'O-ManBlock', 'defense': 'X-43Cover2'} for i in range(24)),
            {'O-ManBlock': 'offense'}, {'formations': [{'index':0, 'name':'Formation 0'}], 'plays': []})

    def test_atomic_clone_scheme_undo_and_saved_recipe_replay(self):
        initial = self.backend.initial
        request = self.facade.playcalling_scheme_plan(0, 'pro_spread')
        self.assertEqual(len(request['assignments']), 1)
        self.stage(request)
        state = self.facade.playcalling_context()['state']
        own = state.teams[0]['offense']
        self.assertNotEqual(own, 'O-ManBlock')
        self.assertEqual(state.books['O-ManBlock'], initial.books['O-ManBlock'])
        self.assertEqual(state.teams[1]['offense'], 'O-ManBlock')
        self.assertEqual(tendency.team_tendency(state.rost, 1), 50)
        self.assertEqual(len(self.facade._playcalling.events(self.facade.session)), 1)
        project = self.facade.session.save_project(self.root/'scheme.apf2k8mod')
        payload = self.facade.playcalling_scheme_csv(0)
        self.assertIn(b'Pro Spread', payload)
        self.facade.undo()
        self.assertFalse(self.facade.session.modifications)
        self.assertEqual(self.facade.playcalling_context()['book'], 'O-ManBlock')
        self.facade.session.load_project(project)
        self.assertEqual(self.facade.playcalling_scheme_csv(0), payload)
        # Applying a second scheme reuses the team's clone and remains one event.
        second = self.facade.playcalling_scheme_plan(0, 'wide_zone')
        self.assertEqual(second['assignments'], [])
        self.stage(second)
        self.assertEqual(self.facade.playcalling_context()['book'], own)

    def test_shared_book_bypass_and_tampered_review_refused(self):
        request = self.facade.playcalling_scheme_plan(0, 'pro_spread')
        with self.assertRaisesRegex(Exception, 'own book'):
            self.facade.playcalling_review(dict(request, assignments=[]))
        review = self.facade.playcalling_review(request)
        review['event']['after']['scheme_receipt']['run_percentage_after'] = 99
        with self.assertRaisesRegex(Exception, 'changed'):
            self.facade.stage_playcalling(review)
        self.assertFalse(self.facade.session.modifications)


if __name__ == '__main__':
    unittest.main(verbosity=2)
