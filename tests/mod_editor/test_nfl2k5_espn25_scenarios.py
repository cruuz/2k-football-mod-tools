"""Standalone bounded authoring, refusal, replay and relocated-image tests."""
import copy
import csv
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tests'):
    sys.path.insert(0, str(path))
from espn25_fixture import fixtures, draft, RETAIL
from mod_editor.core import nfl2k5_espn25_scenarios as e
from nfl2k5_xiso_fixture import SyntheticXiso


def roster_edit(csv_text='pool,index,first,jersey,speed,face\nprimary,0,A,12,91,3\n', **kwargs):
    return {'moment': 0, 'side': 'away', 'shared_resource': True, 'csv': csv_text, **kwargs}


def updated(catalog, outputs):
    return e.Catalog({**catalog.resources, **{i: (catalog.resources[i][0], raw) for i, raw in outputs.items()}}, catalog.manifest)


class AuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = fixtures()

    def test_csv_changes_use_existing_codec_preserve_unknowns_and_replay(self):
        c = self.catalog
        before = c.resource(113)
        plan = c.prepare({'schema': e.SCHEMA, 'rosters': [roster_edit()]})
        outputs, applied = e.resolve_plan(c, plan)
        self.assertFalse(applied)
        self.assertEqual(len(plan['rosters'][0]['shared_uses']), 50)
        self.assertTrue(plan['rosters'][0]['historic_team_outside_mode'])
        changed = updated(c, outputs)
        player = changed.roster_document(0, 'home').players[0]
        self.assertEqual((player.first, player.record.values['jersey'], player.record.values['speed'], player.record.values['face']), ('A', 12, 91, 3))
        self.assertEqual(before[:32], outputs[113][:32])
        mask = e.roster_mask(before, c.manifest['rosters']['113'])
        self.assertTrue(all(not ((a ^ b) & ~m) for a, b, m in zip(before, outputs[113], mask)))
        self.assertTrue(e.resolve_plan(changed, json.loads(json.dumps(plan)))[1])
        self.assertEqual(c.resource(113), before)

    def test_csv_noop_byte_identity(self):
        value = self.catalog.export_csv(0, 'away')
        raw, receipt = self.catalog.import_csv(0, 'away', value)
        self.assertEqual(raw, self.catalog.resource(113))
        self.assertEqual(receipt['changed'], 0)
        self.assertNotIn('college', value.splitlines()[0])

    def test_reopened_name_pool_retains_freed_tail(self):
        raw, _ = self.catalog.import_csv(0, 'away', 'pool,index,last\nprimary,52,A\n')
        changed = updated(self.catalog, {113: raw})
        restored, _ = changed.import_csv(0, 'away', 'pool,index,last\nprimary,52,Last52\n')
        self.assertEqual(restored, self.catalog.resource(113))

    def test_invalid_csv_is_atomic(self):
        cases = [
            'pool,index,jersey\nprimary,0,999\n',
            'pool,index,first\nprimary,0,A\nprimary,0,B\n',
            'pool,index,speed\nprimary,99,50\n',
            'pool,index,speed\nsecondary,0,50\n',
            'pool,index,speed\nprimary,0,101\n',
            'pool,index,first,college\nprimary,0,A,College\n',
            'pool,index,team\nprimary,0,FA\n',
            'pool,index,first\nprimary,0,' + 'X' * 10000 + '\n',
            'pool,index,jersey\nprimary,0,12,extra\n',
            'pool,index,jersey,jersey\nprimary,0,12,13\n',
            'pool,index,first,speed\nprimary,0,A,bad\n',
            'first,last\nName,Name\n',
            'pool,index,first\n',
        ]
        before = self.catalog.resource(113)
        for value in cases:
            with self.subTest(value=value[:70]), self.assertRaises((e.Espn25Error, csv.Error)):
                self.catalog.prepare({'schema': e.SCHEMA, 'rosters': [roster_edit(value)]})
            self.assertEqual(before, self.catalog.resource(113))
        with self.assertRaisesRegex(e.Espn25Error, 'shared_resource'):
            self.catalog.prepare({'schema': e.SCHEMA, 'rosters': [roster_edit(shared_resource=False)]})
        with self.assertRaisesRegex(e.Espn25Error, 'same shared'):
            self.catalog.prepare({'schema': e.SCHEMA, 'rosters': [roster_edit(), roster_edit(side='home')]})

    def test_situ_shortening_reopen_longer_and_setup_units(self):
        c = self.catalog
        edits = {'schema': e.SCHEMA, 'moments': [{'moment': 0, 'text': {'title': 'A'}, 'setup': {
            'human_side': 1, 'possession_side': 0, 'away_score': 17, 'home_score': 14,
            'quarter_index': 3, 'ball_yards': -18.0, 'clock_seconds': 290.0, 'yards_to_gain': 10.0,
            'down': 1, 'home_timeouts': 3}}]}
        outputs, _ = e.resolve_plan(c, c.prepare(edits))
        changed = updated(c, outputs)
        self.assertEqual(changed.moment(0)['text']['title'], 'A')
        self.assertEqual(changed.moment(0)['setup']['clock_seconds'], 290)
        second = changed.prepare({'schema': e.SCHEMA, 'moments': [{'moment': 0, 'text': {'title': 'Longer again'}}]})
        after = updated(changed, e.resolve_plan(changed, second)[0])
        self.assertEqual(after.moment(0)['text']['title'], 'Longer again')
        self.assertEqual(outputs[22][32 + 29104:], c.resource(22)[32 + 29104:])
        self.assertEqual(outputs[22][:32], c.resource(22)[:32])

    def test_team_year_rebinding_applies_csv_to_final_target(self):
        plan = self.catalog.prepare({'schema': e.SCHEMA, 'moments': [{'moment': 0, 'teams': {
            'away': {'selector': 'TEAM01', 'year': 1951}}}], 'rosters': [roster_edit()]})
        self.assertEqual(plan['rosters'][0]['outer'], 114)
        c = updated(self.catalog, e.resolve_plan(self.catalog, plan)[0])
        self.assertEqual(c.binding(0, 'away')['outer'], 114)
        self.assertEqual(c.roster_document(0, 'away').players[0].first, 'A')
        self.assertNotEqual(c.roster_document(0, 'home').players[0].first, 'A')

    def test_schema_refusals_and_conditions(self):
        for edit in ({'moment': 25}, {'moment': True}, {'moment': 0, 'unknown': 1},
                     {'moment': 0, 'setup': {'clock_seconds': float('nan')}},
                     {'moment': 0, 'setup': {'quarter_index': 4}},
                     {'moment': 0, 'setup': {'human_side': True}},
                     {'moment': 0, 'setup': {'weather': 2}},
                     {'moment': 0, 'teams': {'home': {'selector': 'missing', 'year': 1950}}},
                     {'moment': 0, 'text': {'title': 'X' * 100}},
                     {'moment': 0, 'text': {'date': '\0'}},
                     {'moment': 0, 'conditions_from_moment': 25}):
            with self.subTest(edit=edit), self.assertRaises(e.Espn25Error):
                self.catalog.prepare({'schema': e.SCHEMA, 'moments': [edit]})
        plan = self.catalog.prepare({'schema': e.SCHEMA, 'moments': [{'moment': 0, 'conditions_from_moment': 1}]})
        self.assertTrue(e.resolve_plan(self.catalog, plan)[1])
        with self.assertRaises(e.Espn25Error):
            self.catalog.prepare({'schema': e.SCHEMA, 'moments': [{'moment': 0}, {'moment': 0}]})

    def test_foreign_layouts_and_pointers_refuse(self):
        for index, offset, value in ((113, 20, 1), (113, 32 + 972, 1), (113, 32 + 472, 1),
                                     (22, 20, 1), (22, 32 + 64, 30), (22, len(self.catalog.resource(22)) - 1, 0),
                                     (5, 32 + 0x100, 1)):
            with self.subTest(index=index, offset=offset):
                raw = bytearray(self.catalog.resource(index)); raw[offset] = value
                with self.assertRaises(e.Espn25Error):
                    updated(self.catalog, {index: bytes(raw)})
        raw = bytearray(self.catalog.resource(113))
        struct.pack_into('<i', raw, 32 + 972 + 16, 1)
        with self.assertRaisesRegex(e.Espn25Error, 'pool'):
            updated(self.catalog, {113: bytes(raw)})

    def test_replay_refuses_mixed_stale_tampered_and_protected_bytes(self):
        c = self.catalog
        plan = c.prepare({'schema': e.SCHEMA, 'moments': [{'moment': 0, 'setup': {'home_score': 14}}], 'rosters': [roster_edit()]})
        outputs, _ = e.resolve_plan(c, plan)
        with self.assertRaisesRegex(e.Espn25Error, 'mixed'):
            e.resolve_plan(updated(c, {113: outputs[113]}), plan)
        stale = c.prepare({'schema': e.SCHEMA, 'moments': [{'moment': 1, 'text': {'title': 'Stale'}}]})
        with self.assertRaisesRegex(e.Espn25Error, 'stale'):
            e.resolve_plan(updated(c, e.resolve_plan(c, stale)[0]), plan)
        bad = copy.deepcopy(plan); bad['resources'][0]['after_sha256'] = '0' * 64
        with self.assertRaises(e.Espn25Error): e.resolve_plan(c, bad)
        raw = bytearray(c.resource(113)); raw[20] = 1
        bad = copy.deepcopy(plan); bad['resources'][1] = e.resource_plan(113, c.resources[113][0], c.resource(113), bytes(raw))
        with self.assertRaises(e.Espn25Error): e.resolve_plan(c, bad)

    def test_research_30_layout_and_install_refusal(self):
        table = self.catalog.research_table(draft(self.catalog))
        self.assertEqual((e.u32(table, 8), e.u32(table, 32 + 64)), (30, 30))
        self.assertEqual(e.u32(table, 4), len(table) - 32)
        self.assertEqual(len(table) % 16, 0)
        body = table[32:]
        for i in range(30):
            for offset in e.POINTERS:
                target = e.rel(body, e.RECORDS + i * e.STRIDE + offset)
                self.assertGreaterEqual(target, e.RECORDS + 30 * e.STRIDE)
                self.assertTrue(e.utf16(body, target))
        self.assertEqual(e.utf16(body, e.rel(body, e.RECORDS + 29 * e.STRIDE)), 'Authored test 4')
        with self.assertRaisesRegex(e.Espn25Error, 'expanded'):
            self.catalog.prepare(draft(self.catalog))
        with self.assertRaises(e.Espn25Error): self.catalog.research_table(draft(self.catalog, 8))
        bad = draft(self.catalog); del bad['append'][0]['setup']['clock_seconds']
        with self.assertRaises(e.Espn25Error): self.catalog.research_table(bad)

    def test_bounded_json_rejects_duplicates_nonfinite_and_oversize(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / 'edits.json'
            for text in ('{"schema":1,"schema":2}', '{"x":NaN}', 'x' * (e.MAX_JSON + 1)):
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(e.Espn25Error): e.read_json(path)


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='espn25-test-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        c = self.catalog = fixtures()
        manifest = self.directory / 'layout.json'; e.write_json(manifest, c.manifest)
        patch = mock.patch.object(e, 'MANIFEST', manifest); patch.start(); self.addCleanup(patch.stop)
        entries = [c.resources.get(i, (0xA0000000 + i, bytes(32))) for i in range(189)]
        # Real archive/XDVDFS format; pack moved to sector 512, entire fixture <4 MiB.
        self.fixture = SyntheticXiso(self.directory, entries, pack_sizes=(2 * 1024 * 1024,), pack_sectors=(512,))
        self.plan = c.prepare({'schema': e.SCHEMA, 'moments': [{'moment': 0, 'setup': {'home_score': 14}}], 'rosters': [roster_edit()]})

    def test_relocated_image_receipts_replay_and_siblings(self):
        image = self.fixture.path
        with e.rr._outer_image()(image) as archive:
            before = {i: archive.read_entry(i) for i in (5, 22, 113, 114, 188)}
        self.assertEqual(e.status(image, self.plan), 'ready')
        receipt = e.apply_to_image(image, self.plan)
        self.assertFalse(receipt['already_applied']); self.assertFalse(receipt['xbe_changed'])
        with e.rr._outer_image()(image) as archive:
            for i in (5, 114, 188): self.assertEqual(archive.read_entry(i), before[i])
            for row in receipt['resources']:
                after = archive.read_entry(row['outer'])
                self.assertEqual(e.sha(after), row['after_sha256'])
            self.assertEqual(archive.read_entry(22)[32 + 29104:], before[22][32 + 29104:])
        self.assertTrue(e.apply_to_image(image, self.plan)['already_applied'])
        self.assertEqual(e.status(image, self.plan), 'applied')

    def test_mixed_and_foreign_source_no_writes(self):
        outputs, _ = e.resolve_plan(self.catalog, self.plan)
        with e.rr._outer_image()(self.fixture.path, writable=True) as archive:
            archive.write(archive.entries[113].virtual_offset, outputs[113])
        outer = e.rr._outer_image()
        with mock.patch.object(outer, 'write', side_effect=AssertionError('unexpected write')):
            with self.assertRaisesRegex(e.Espn25Error, 'mixed'):
                e.apply_to_image(self.fixture.path, self.plan)

    def test_transactional_build_short_write_cleanup_and_success(self):
        output = self.directory / 'output.iso'
        outer = e.rr._outer_image()
        with mock.patch.object(e.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(e.Espn25Error, '100 GB'):
                e.build_image(self.fixture.path, output, self.plan)
        self.assertFalse(output.exists())
        # The <4 MiB synthetic fixture must also run on small CI runners.
        capacity = mock.patch.object(e.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024**4))
        capacity.start(); self.addCleanup(capacity.stop)
        with mock.patch.object(outer, 'write', return_value=0):
            with self.assertRaisesRegex(e.Espn25Error, 'short'):
                e.build_image(self.fixture.path, output, self.plan)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.directory.glob('espn25-build-*')))
        self.assertEqual(e.status(self.fixture.path, self.plan), 'ready')
        failed_descriptors = []
        def fail_sync(descriptor):
            failed_descriptors.append(descriptor)
            raise OSError('fixture fsync failure')
        with mock.patch.object(e.os, 'fsync', side_effect=fail_sync), mock.patch.object(e.os, 'close', wraps=os.close) as close:
            with self.assertRaisesRegex(OSError, 'fsync failure'):
                e.build_image(self.fixture.path, output, self.plan)
            for descriptor in failed_descriptors:
                self.assertIn(mock.call(descriptor), close.call_args_list)
                with self.assertRaises(OSError):
                    os.fstat(descriptor)
        self.assertTrue(failed_descriptors)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.directory.glob('espn25-build-*')))
        receipt = e.build_image(self.fixture.path, output, self.plan)
        self.assertFalse(receipt['already_applied'])
        self.assertEqual(e.status(output, self.plan), 'applied')
        self.assertEqual(e.status(self.fixture.path, self.plan), 'ready')
        with self.assertRaises(e.Espn25Error): e.build_image(self.fixture.path, output, self.plan)

    def test_constructor_failure_closes_source(self):
        outer = e.rr._outer_image()
        with mock.patch.object(outer, '_read_table', side_effect=ValueError('broken table')):
            with self.assertRaises(ValueError): e.Catalog.load(self.fixture.path)
        target = self.directory / 'renamed.iso'
        os.replace(self.fixture.path, target)  # also catches a leaked Windows handle
        self.assertTrue(target.exists())


class RetailEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RETAIL / 'vc_53450030/0').is_file():
            raise unittest.SkipTest('retail extracted vc_53450030/0 absent; synthetic tests remain active')
        cls.catalog = e.Catalog.load(RETAIL)

    def test_all_50_bindings_and_75_rosters(self):
        c = self.catalog
        self.assertEqual(len(c.descriptors), 75)
        self.assertEqual(len({c.binding(i, s)['outer'] for i in range(25) for s in ('away', 'home')}), 35)
        expected = [(125,133),(155,157),(141,139),(157,163),(141,158),(183,126),(149,171),(169,142),
                    (126,171),(159,183),(129,187),(172,124),(177,113),(124,172),(118,153),(181,129),
                    (140,129),(181,118),(129,140),(136,118),(134,130),(167,182),(167,147),(154,174),(135,162)]
        self.assertEqual([(c.binding(i,'away')['outer'],c.binding(i,'home')['outer']) for i in range(25)], expected)
        for descriptor in c.descriptors:
            doc = c.validate_roster(descriptor['outer'], c.resource(descriptor['outer']))
            self.assertEqual((len(doc.players), doc.teams[0].player_count), (53,53))

    def test_real_csv_edit_and_plan_replay(self):
        c = self.catalog
        for moment in range(25):
            for side in ('away', 'home'):
                raw, result = c.import_csv(moment, side, c.export_csv(moment, side))
                self.assertEqual(raw, c.resource(c.binding(moment,side)['outer']))
                self.assertEqual(result['changed'], 0)
        plan = c.prepare({'schema': e.SCHEMA, 'rosters': [roster_edit('pool,index,first,last,jersey,position,speed,skin,face\nprimary,0,A,B,12,QB,91,2,3\n')]})
        outputs, _ = e.resolve_plan(c, plan)
        self.assertTrue(e.resolve_plan(updated(c, outputs), plan)[1])


if __name__ == '__main__':
    unittest.main()
