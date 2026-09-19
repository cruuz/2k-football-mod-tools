"""Version 2 authored transport and project lifecycle, no retail bytes."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_situation_mask as mask
from mod_editor.core.errors import ValidationError
from mod_editor.apf_studio import situation_masks as transport
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture


def rows(name='O-ManBlock', key=8, values=None):
    result = {name: [{} for _ in range(12)]}
    result[name][key] = {'6': 10} if values is None else values
    return result


class DataTests(unittest.TestCase):
    def test_v2_roundtrip_both_profiles_and_v1_read_compatibility(self):
        policies = {'O-ManBlock': [[] for _ in range(12)]}
        policies['O-ManBlock'][8] = [2, 24]
        for overrides in ({}, rows(), rows('USER-o')):
            data = mask.encode_data(policies, overrides)
            self.assertEqual(len(data), 13824)
            self.assertEqual(mask.decode_data(data, include_personnel_rows=True), (policies, overrides))
            self.assertEqual(mask.encode_data(*mask.decode_data(data, include_personnel_rows=True)), data)
            for profile in mask.PROFILES:
                patch = mask.SituationPatch(profile, data)
                self.assertEqual(patch.receipt['schema'], mask.SCHEMA)
                self.assertEqual(patch.receipt['personnel_rows'], overrides)
                self.assertEqual(mask.canonical_payload(patch.as_toml().encode()), (profile, True))
                self.assertEqual(len(mask.assemble(profile, 2)[1]), 3)
                self.assertLessEqual(mask.CODE_START + len(mask.assemble(profile, 2)[0]), mask.CODE_LIMIT)
        self.assertEqual(mask.decode_data(mask.encode_data(policies)), policies)
        self.assertEqual(mask.decode_personnel_rows(mask.encode_data(policies)), {})

    def test_sparse_capacity_and_invalid_values_fail_before_writing(self):
        policies = {f'Book{i:02}': [[i] for _ in range(12)] for i in range(48)}
        data = mask.encode_data(policies, rows('Book00'))
        self.assertEqual(mask.decode_personnel_rows(data), rows('Book00'))
        crowded = {name: [{str(i): 10 for i in range(28)} for _ in range(12)] for name in policies}
        with self.assertRaisesRegex(ValidationError, 'storage is full'):
            mask.encode_data(policies, crowded)
        for value in (-1, 11, True, '10', 1.5):
            with self.assertRaises(ValidationError):
                mask.encode_data({}, rows(values={'6': value}))
        self.assertEqual(mask.decode_personnel_rows(mask.encode_data({}, rows(values={'6': None}))), {})
        source = mask.encode_data({}, rows())
        # Unknown version, sparse count, book/key/category/row and padding.
        for offset in (7, 16 + 268, 16 + 268 + 4, 16 + 268 + 5, 16 + 268 + 6, 16 + 268 + 7, len(source)-1):
            data = bytearray(source); data[offset] = 255
            with self.assertRaises(ValidationError):
                mask.decode_data(bytes(data))


class ModelFixtureTests(unittest.TestCase):
    def setUp(self):
        from tests.mod_editor.test_apf_b67_writers import WritersTests
        from tests.mod_editor.test_apf_formation_alignment_writer import _synthetic_master
        from mod_editor.core import apf2k8_splb_writer as splb
        fixture = WritersTests(); fixture.setUp()
        body = splb.set_formation_categories(fixture.book, 0, 6, ())
        body = splb.set_formation_categories(body, 1, 8, ())
        self.book = splb.set_formation_ratings(body, 0, (7, 7, 7))
        master = bytearray(_synthetic_master(formation_count=163, category_count=28))
        for i in range(28):
            at = 0x44 + 16*i
            name = ('Queens' if i == 6 else f'Personnel {i}').encode('utf-16-be') + bytes(2)
            target = 0x2B000 + i*64
            struct.pack_into('>i', master, at, target-at+1)
            master[at+4] = min(i, 27)
            master[target:target+len(name)] = name
        self.master = bytes(master)

    def test_all_bucket_decomposition_and_minimum_rating_sole_candidate(self):
        from mod_editor.core import apf2k8_playcall_model as model
        for down in range(1, 5):
            for distance in (1, 5, 8):
                s = model.Situation(down, distance, 50, 1, 900, 0, 3)
                row = model.requested_offense_row(s)
                candidates = model.situation_candidates(self.book, self.master, s, personnel_rows={'6': 10})
                weights = dict(model.category_weights(self.book, self.master, row, s, personnel_rows={'6': 10}))
                unique = {c['category']: c for c in candidates}
                self.assertEqual(sum(weights.values()), sum(c['category_weight'] for c in unique.values()))
                for c in candidates:
                    self.assertEqual(model.f32(c['curve_term']*c['ratings_term']), weights[c['category']])
        s = model.Situation(3, 8, 50, 1, 900, 0, 3)
        categories, fallback = mask.filter_categories(self.book, self.master,
            model.category_weights(self.book, self.master, 10, s, personnel_rows={'6': 10}), [1])
        self.assertFalse(fallback)
        shown = model.situation_candidates(self.book, self.master, s, personnel_rows={'6': 10}, exclusions=[1])
        excluded = next(c for c in shown if c['formation'] == 1)
        self.assertFalse(excluded['active'])
        self.assertFalse(excluded['fallback'], 'A removed category never reaches the formation fallback')
        self.assertEqual(categories, ((6, model.f32(.1)),))
        formations = model.formation_weights(self.book, self.master, 6, s)
        self.assertEqual(formations, ((0, model.f32(.1)),))
        for fraction in (0., .001, .25, .5, .99, .999999):
            self.assertEqual(model.draw(categories, fraction, power=3), 6)
            self.assertEqual(model.draw(formations, fraction), 0)
        self.assertTrue(all(c["effective_row"] == c["stored_row"] for c in
                            model.category_weight_terms(self.book, self.master, 25, s, personnel_rows={"6": 10})))
        self.assertEqual(model.category_weights(self.book, self.master, 10, s),
                         model.category_weights(self.book, self.master, 10, s, personnel_rows={'6': 'unknown'}))


class ProjectTests(FacadeFixture):
    def test_local_override_staging_reload_undo_and_build_receipts(self):
        from mod_editor.apf_studio.playcalling_service import LINEUP_CALLERS
        self.backend.lineup_callers = LINEUP_CALLERS
        engine, session = self.facade._playcalling, self.facade.session
        initial = engine.state(session)
        self.assertFalse(initial.situation_masks_enabled)
        self.assertEqual(initial.situation_personnel_rows, {})
        request = dict(kind='situation_personnel_row', book='O-ManBlock', key=8, category=6, value=10)
        for edit in (dict(kind='situation_masks_enabled', enabled=True), request):
            self.stage(edit)
        state = engine.state(session)
        self.assertEqual(state.master, initial.master)
        self.assertEqual(state.books, initial.books)
        self.assertEqual(state.situation_personnel_rows, rows())
        with tempfile.TemporaryDirectory() as directory:
            receipt = transport.export_build(Path(directory), state)
            for patch in receipt['patches']:
                self.assertEqual(patch['personnel_rows'], rows())
                mask.canonical_payload((Path(directory) / patch['file']).read_bytes())
            self.assertEqual(mask.decode_personnel_rows((Path(directory) / receipt['data']).read_bytes()), rows())
        project = session.save_project(self.root / 'local-rows.apf2k8mod')
        session.undo()
        self.assertEqual(engine.state(session).situation_personnel_rows, {})
        session.load_project(project)
        self.assertEqual(engine.state(session).situation_personnel_rows, rows())
        self.stage({**request, 'value': None})
        self.assertEqual(engine.state(session).situation_personnel_rows, {})
        session.undo()
        self.assertEqual(engine.state(session).situation_personnel_rows, rows())
        # A policy edit followed by a cached edit cannot discard the other policy.
        self.stage(dict(kind='situation_mask', book='O-ManBlock', key=8, formation=62, exclude=True))
        self.stage({**request, 'key': 7})
        self.assertEqual(engine.state(session).situation_masks['O-ManBlock'][8], [62])
        self.stage(dict(kind='situation_masks_enabled', enabled=False))
        self.assertEqual(transport.prepare(engine.state(session), 'base')['receipt']['personnel_rows'], {})
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(transport.export_build(Path(directory), engine.state(session)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
