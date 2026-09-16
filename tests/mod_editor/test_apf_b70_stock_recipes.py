"""Stock replacement writes, refusal, project persistence and copied build readback."""
from pathlib import Path
import hashlib
import json
import os
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio import scheme_service as service, build, playcalling_service, book_content
from mod_editor.apf_studio.models import ApfSource
from mod_editor.apf_studio.session import ApfSession
from mod_editor.core import apf2k8_splb_writer as splb, apf2k8_book_clone as clone
from mod_editor.core.apf2k8_book_identity import read_resource, filename_id
from mod_editor.core.errors import ValidationError
from tests.mod_editor import test_apf_book_unlock as fixture
from tests.mod_editor.test_apf2k8_playbook_route_writer import _synthetic_master


def master_body():
    """A fully parseable authored MASTER, including names and slot pointers."""
    body = bytearray(_synthetic_master())
    inventory = service.playbook_inventory
    struct.pack_into('>IIII', body, 0x34, 3, 6, 28, 2)
    body[inventory.APF_STRING_BASE:inventory.APF_FORMATION_MEMBERSHIP_BASE] = bytes(
        inventory.APF_FORMATION_MEMBERSHIP_BASE - inventory.APF_STRING_BASE)
    cursor = inventory.APF_STRING_BASE
    def name(field, value):
        nonlocal cursor
        text = (value+'\0').encode('utf-16-be')
        body[cursor:cursor+len(text)] = text
        struct.pack_into('>i', body, field, cursor-field+1)
        cursor += len(text)
    name(0x30, 'MASTER')
    for i in range(28):
        at = inventory.APF_CATEGORY_BASE + i*16
        name(at, f'Category {i}')
        body[at+4] = splb.PERSONNEL_ROWS[i]
        body[at+5:at+16] = bytes((0,5,5,6,7,7,10,8,9,9,9))
    for i in range(3):
        name(inventory.APF_FORMATION_BASE+i*inventory.APF_FORMATION_SIZE, f'Formation {i}')
    for i in range(6):
        at = inventory.APF_PLAY_BASE+i*inventory.APF_PLAY_SIZE
        name(at, f'Play {i}')
        struct.pack_into('>II', body, at+4, 0, 2 if i%2 else 8)
        for slot in range(inventory.SLOT_COUNT):
            pointer = at+0x10+slot*8
            struct.pack_into('>i', body, pointer, inventory.APF_ROUTE_BASE-pointer+1)
    inventory.parse_apf_body(bytes(body), 180, 0)
    return bytes(body)


def book_body(name):
    body = bytearray(fixture.book_body(name))
    row = bytes(body[0x70:0x120])
    for i, category in enumerate((0, 3, 7)):
        at = 0x70 + i * 176
        body[at:at+176] = row
        struct.pack_into('>II', body, at+168, i<<24 | category<<17 | 0x9200, 1<<category)
    if name == 'O-ManBlock':
        # A target-only play must disappear on replacement, including its cache bit.
        struct.pack_into('>H', body, 0x70+10, 2<<13 | 4<<10 | 55)
    return splb._compact_normalize(bytes(body))


class StockRecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # The archive fixture resolves its body factory dynamically.
        original_factory = fixture.book_body
        def factory(name):
            with patch.object(fixture, 'book_body', original_factory):
                return book_body(name)
        with patch.object(fixture, 'book_body', factory):
            self.index = fixture.archive_fixture(self.root/'game')
        self.master = master_body()
        self.master_patch = patch.object(service, 'read_master_play_body', return_value=self.master)
        self.master_patch.start()
        self.addCleanup(self.master_patch.stop)
        tree = {p.name: (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()) for p in self.index.parent.iterdir()}
        self.tree = tree
        self.source = ApfSource(self.index.parent, self.index.parent, self.index, tree['0A'][1], tree['0A'][0],
                                tree['default.xex'][1], 'synthetic')
        self.session = ApfSession(self.source, SimpleNamespace(), cache_root=self.root/'cache')
        self.addCleanup(self.session.close)

    def test_off_by_default_explicit_book_persistence_undo_and_tamper(self):
        self.assertFalse(self.session.modifications)
        service.stage_replacement(self.session, 'O-ManBlock', 'air_coryell')
        service.stage_replacement(self.session, 'USER-o', 'pro_spread')
        profiles = service.read_profile(self.session.modifications[0])
        self.assertEqual([p['book_type'] for p in profiles], ['O-ManBlock', 'USER-o'])
        project = self.root/'recipes.apf2k8mod'
        self.session.save_project(project)
        self.session.load_project(project)
        self.assertEqual(service.read_profile(self.session.modifications[0]), profiles)
        service.stage_replacement(self.session, 'USER-o', 'west_coast')
        self.assertTrue(self.session.undo())
        self.assertEqual(service.read_profile(self.session.modifications[0]), profiles)
        profile = self.session.modifications[0]
        profile.replacement_path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValidationError, 'changed after staging'):
            service.read_profile(profile)

    def test_real_copied_build_receipt_reparses_whole_replacement_and_other_books(self):
        original = self.index.read_bytes()
        reports = service.stage_replacement(self.session, 'O-ManBlock', 'air_coryell')
        self.assertIn(55, reports[0]['before_content'][0]['plays'])
        self.assertTrue(all(55 not in r['plays'] for r in reports[0]['after_content']))
        with patch.object(book_content, 'master_inventory', return_value=({}, self.master)):
            state = playcalling_service.Backend().load(self.session)
        self.assertEqual(hashlib.sha256(state.books['O-ManBlock']).hexdigest(), reports[0]['output_sha256'])
        with patch.object(build, 'EXPECTED_TREE', self.tree), patch.object(build, 'EXPECTED_0A_SHA256', self.source.source_sha256):
            result = build.ApfBuildService(self.source).build(self.session.modifications, self.root/'output')
        output = self.root/'output/0A'
        body = read_resource(output, filename_id('O-ManBlock'), 'spb', 'SPLB')[3]
        self.assertEqual(hashlib.sha256(body).hexdigest(), reports[0]['output_sha256'])
        self.assertEqual(self.index.read_bytes(), original)
        donor_before = read_resource(self.index, filename_id('O-TwoBack'), 'spb', 'SPLB')[3]
        self.assertEqual(read_resource(output, filename_id('O-TwoBack'), 'spb', 'SPLB')[3], donor_before)
        self.assertTrue(result.manifest.is_file())
        self.assertIn('replaced_entire_content', result.manifest.read_text())
        self.assertIn('UNWITNESSED', result.manifest.read_text())
        # Another replacement targets the first recipe's donor. Preview must
        # continue to use the source donor, matching the build's order policy.
        combined = service.stage_replacement(self.session, 'O-TwoBack', 'pro_spread')
        with patch.object(book_content, 'master_inventory', return_value=({}, self.master)):
            state = playcalling_service.Backend().load(self.session)
        for report in combined:
            self.assertEqual(hashlib.sha256(state.books[report['book_type']]).hexdigest(), report['output_sha256'])

    def test_capacity_refusal_is_atomic_and_names_next_step(self):
        with patch.object(service, 'rebuild_resource', side_effect=ValidationError('Rebuilt IFF needs 5000 bytes; allocation is 2048')):
            with self.assertRaisesRegex(ValidationError, 'O-ManBlock cannot hold.*another stock book'):
                service.stage_replacement(self.session, 'O-ManBlock', 'air_coryell')
        self.assertFalse(self.session.modifications)
        self.assertFalse(self.session.undo())

    def test_foreign_duplicate_and_conflicting_fine_tune_requests_refuse(self):
        recipe = service.replacement_recipe('O-ManBlock', 'air_coryell')
        for rows in ([recipe, recipe], [dict(recipe, extra=True)], [dict(recipe, book_type='global-o')]):
            with self.assertRaises(ValidationError):
                service.validate_payload(json.dumps({'schema': service.SCHEMA, 'presets': rows}).encode(),
                                         service.SELECTOR, {'schema': service.SCHEMA})
        outer = read_resource(self.index, filename_id('O-ManBlock'), 'spb', 'SPLB')[1].table_index
        with self.assertRaisesRegex(ValidationError, 'Fine-tune edits'):
            service.compile_recipes(self.index, [recipe], [splb.MembershipChange(outer, 0, 55, False)])


class RetailRecipeTests(unittest.TestCase):
    def test_all_eight_schemes_on_all_eight_targets_fit_or_name_capacity(self):
        index = Path(os.environ.get('APF_RETAIL_INDEX', '/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A'))
        if not index.is_file():
            self.skipTest(f'APF_RETAIL_INDEX absent: {index}')
        fit = refused = 0
        for name in service.STOCK_TARGETS:
            for scheme in service.SCHEME_CONTENT:
                with self.subTest(book=name, scheme=scheme):
                    try:
                        rows = service.compile_recipes(index, [service.replacement_recipe(name, scheme)])
                    except ValidationError as exc:
                        self.assertIn('cannot hold', str(exc))
                        self.assertIn('allocation', str(exc))
                        refused += 1
                    else:
                        report = rows[0][2]
                        self.assertTrue(report['verification']['donor_membership_reparsed'])
                        self.assertTrue(report['transport']['h7a_round_trip_exact'])
                        fit += 1
        self.assertEqual(fit+refused, 64)
        self.assertGreater(fit, 0)
        # A legal refit may fit all 64 recipes. Actual overflow and atomic
        # refusal have their own synthetic tests; do not require a fit miss.
        print(f'PROVED retail replacement matrix: {fit} fits, {refused} named capacity refusals')


if __name__ == '__main__':
    unittest.main()
