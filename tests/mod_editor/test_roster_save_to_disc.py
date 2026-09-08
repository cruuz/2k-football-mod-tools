"""Bounded synthetic disc/save proofs for the actual Build roster-edits consumer."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests/mod_editor'), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_roster_save_to_disc as importer
from tests.mod_editor.test_nfl2k5_roster_records import (
    league_body, league_sample, synthetic_body, synthetic_resource, synthetic_save_v0,
    retail_front_body, reclassified_retail_body, retail_body, HAVE_RETAIL,
)
from tests.nfl2k5_xiso_fixture import SyntheticXiso


def signed(body: bytes, *, runtime=True) -> rr.RosterDocument:
    payload = synthetic_save_v0(body) if runtime else body
    container = rr.SaveContainer('loose', Path('source/SAVEGAME.DAT'),
        {'SAVEGAME.DAT': payload, 'EXTRA': rr.sign_save(payload)}, 'SAVEGAME.DAT', 'EXTRA', True)
    return container.document()


def save_files(directory: Path, doc: rr.RosterDocument) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    payload = doc.to_body()
    (directory / 'SAVEGAME.DAT').write_bytes(payload)
    (directory / 'EXTRA').write_bytes(rr.sign_save(payload))
    return directory / 'SAVEGAME.DAT'


def image_fixture(directory: Path, body: bytes) -> SyntheticXiso:
    return SyntheticXiso(directory, [(100+i, b'unchanged' * 8) for i in range(5)]
        + [(0x12345678, synthetic_resource(body)), (200, b'neighbor' * 128)],
        pack_sizes=(0xA0000,), pack_sectors=(64,))


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.disc = rr.load_body(league_body())
        self.save = signed(self.disc.to_body())

    def replay(self, result):
        body, receipt = rr.apply_body(self.disc.to_body(), result.edits, scheme=self.disc.scheme)
        self.assertEqual(receipt['log'], [])
        self.assertEqual(hashlib.sha256(body).hexdigest(), result.receipt['result_body_sha256'])
        return rr.load_body(body, scheme=self.disc.scheme)

    def test_loaded_unedited_save_exports_whole_roster_and_replays_on_real_image_adapter(self):
        save = self.save
        p, q = save.players[0], save.players[44]
        save.swap(p, q)
        save.release(save.players[1])
        save.sign(save.players[88], 1, slot=2)
        save.set_name(p, 'first', 'New')
        save.set_name(p, 'last', 'Name')
        for k, v in dict(jersey=99, position=3, speed=97, helmet=1, contract_value=650,
                         contract_remaining=4, depth_rank=2, depth_side=1, unknown_52=0x20).items():
            p.record.set(k, v)
        save.set_college(p, 1)
        save.teams[1].slots.reverse()
        save._reindex_membership()
        # Loading the completed community save leaves zero editor-session diffs.
        save = signed(save.to_body(), runtime=False)
        self.assertFalse(rr.edits_document(save)['edits'])
        source_before = save.to_body()
        disc_before = self.disc.to_body()
        result = importer.compare(self.disc, save)
        self.assertGreater(result.receipt['changed'], 4)
        self.assertEqual(result.receipt['unmatched'], 0)
        self.assertEqual(result.receipt['skipped'], [])
        again = importer.compare(self.disc, save)
        self.assertEqual(importer.json_text(result.edits), importer.json_text(again.edits))
        self.assertEqual(result.details, again.details)
        self.assertEqual(source_before, save.to_body())
        self.assertEqual(disc_before, self.disc.to_body())
        target = self.replay(result)
        for old, new in zip(save.players, target.players):
            self.assertEqual((old.first, old.last, old.college), (new.first, new.last, new.college))
            for field in importer.CARRIED_FIELDS:
                self.assertEqual(old.record.values[field], new.record.values[field], (old.index, field))
            self.assertEqual(old.teams, new.teams)
        for s, t in zip(save.teams, target.teams):
            self.assertEqual([save.by_offset[o].index for o in s.slots],
                             [target.by_offset[o].index for o in t.slots])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            fixture = image_fixture(root, self.disc.to_body())
            old_image = fixture.path.read_bytes()  # explicitly bounded below 1 MiB
            self.assertLess(len(old_image), 1024 * 1024)
            edit_path = root / 'roster_edits.json'
            edit_path.write_text(importer.json_text(result.edits))
            result.write_receipt(edit_path)
            rr.apply(fixture.path, edit_path, scheme='retail')
            reread = rr.load_image(fixture.path)
            self.assertEqual(reread.to_body(), target.to_body())
            new_image = fixture.path.read_bytes()
            start = fixture.virtual_to_image(fixture.entry_offsets[5]) + rr.RESOURCE_HEADER_SIZE
            self.assertEqual(old_image[:start], new_image[:start])
            self.assertEqual(old_image[start+len(disc_before):], new_image[start+len(disc_before):])
            rr.apply(fixture.path, edit_path, scheme='retail')
            self.assertEqual(fixture.path.read_bytes(), new_image)

    def test_pure_depth_order_keeps_locks_and_rank_even_without_field_changes(self):
        self.save.teams[0].slots[:3] = self.save.teams[0].slots[1:3] + self.save.teams[0].slots[:1]
        result = importer.compare(self.disc, self.save)
        target = self.replay(result)
        self.assertTrue(result.edits['moves'])
        self.assertEqual([target.by_offset[o].index for o in target.teams[0].slots[:3]], [1, 2, 0])
        for p in target.players:
            for k in importer.DEPTH_FIELDS:
                self.assertEqual(p.record.values[k], self.save.players[p.index].record.values[k])

    def test_current_target_bytes_are_baseline_and_existing_session_edits_are_carried(self):
        self.disc.players[0].record.set('speed', 70)
        self.save.players[0].record.set('speed', 91)
        result = importer.compare(self.disc, self.save)
        self.assertEqual(result.edits['source_body_sha256'], hashlib.sha256(self.disc.to_body()).hexdigest())
        self.assertEqual(self.replay(result).players[0].record.get('speed'), 91)

    def test_names_too_long_are_skipped_without_truncation_or_neighbor_damage(self):
        # A separately loaded save owns a larger allocation than the target disc.
        rows = league_sample()
        row = list(rows[0]); row[0] = 'AnImpossiblyLongGivenName'; rows[0] = tuple(row)
        source = signed(synthetic_body(rows))
        source.players[0].record.set('jersey', 98)
        result = importer.compare(self.disc, source)
        target = self.replay(result)
        self.assertEqual(target.players[0].first, self.disc.players[0].first)
        self.assertEqual(target.players[0].record.get('jersey'), 98)
        self.assertTrue(any(s['field'] == 'first' and 'never truncated' in s['reason'] for s in result.receipt['skipped']))
        self.assertEqual(target.players[1].first, self.disc.players[1].first)

    def test_unique_names_match_reordered_records_before_rename_fallback(self):
        rows = league_sample()
        rows[0], rows[1] = rows[1], rows[0]
        source = signed(synthetic_body(rows))
        source.players[0].record.set('speed', 98)
        result = importer.compare(self.disc, source)
        self.assertEqual(self.replay(result).players[1].record.get('speed'), 98)
        self.assertEqual(result.receipt['unmatched'], 0)

    def test_ambiguous_names_are_skipped_and_no_ordinal_guess_is_made(self):
        rows = league_sample()
        rows[1] = rows[0]
        disc = rr.load_body(synthetic_body(rows))
        for p in disc.players[:2]: p.record.set('pbp_id', 555)
        source = signed(disc.to_body())
        source.players[0].record.set('speed', 99)
        result = importer.compare(disc, source)
        self.assertEqual(result.receipt['unmatched'], 2)
        self.assertTrue(all('Ambiguous' in s['reason'] for s in result.receipt['skipped']))
        self.assertFalse(result.edits['edits'])

    def test_star_and_team_disambiguation_and_pool_separation(self):
        rows = league_sample()
        r = list(rows[44]); r[:2] = rows[0][:2]; rows[44] = tuple(r)
        disc = rr.load_body(synthetic_body(rows))
        disc.players[44].record.set('pbp_id', disc.players[0].record.get('pbp_id'))
        disc.players[44].record.set('star_tag', 1)
        source = signed(disc.to_body())
        source.players[44].record.set('speed', 98)
        result = importer.compare(disc, source)
        self.assertEqual(result.receipt['unmatched'], 0)
        body, _ = rr.apply_body(disc.to_body(), result.edits, scheme='retail')
        self.assertEqual(rr.load_body(body).players[44].record.get('speed'), 98)

    def test_pooled_disc_refuses_retail_save_with_exact_code_reason(self):
        self.disc.set_scheme('one_pool')
        with self.assertRaisesRegex(importer.SaveToDiscError, 'Position scheme mismatch: disc uses one_pool; Xbox save uses retail') as err:
            importer.compare(self.disc, self.save)
        self.assertIn('code 10', str(err.exception))
        self.assertIn('no conversion was exported', str(err.exception))

    def test_edge_labels_share_retail_code_meanings(self):
        self.disc.set_scheme('edge')
        result = importer.compare(self.disc, self.save)
        self.assertFalse(result.edits['edits'])

    def test_unsigned_or_tampered_loaded_save_refuses(self):
        self.save.container.verified = False
        with self.assertRaisesRegex(importer.SaveToDiscError, 'signature-verified'):
            importer.compare(self.disc, self.save)
        self.save.container.verified = True
        self.save.container.members['EXTRA'] = bytes(20)
        with self.assertRaisesRegex(importer.SaveToDiscError, 'signature no longer'):
            importer.compare(self.disc, self.save)

    def test_capacity_65_and_overflow_and_minimum_batch_refusal(self):
        self.disc = rr.load_body(league_body(64))
        self.save = signed(self.disc.to_body())
        self.save.sign(self.save.players[128], 0, maximum=65)
        result = importer.compare(self.disc, self.save)
        self.assertEqual(len(self.replay(result).teams[0].slots), 65)
        bad = bytearray(self.save.to_body())
        bad[self.save.teams[0].offset + rr.TEAM_PLAYER_COUNT] = 66
        with self.assertRaisesRegex(importer.SaveToDiscError, '65 pointer slots'):
            importer.compare(self.disc, signed(bytes(bad), runtime=False))
        self.disc = rr.load_body(league_body(42))
        self.save = signed(self.disc.to_body())
        self.save.release(self.save.players[0], minimum=0)
        result = importer.compare(self.disc, self.save)
        self.assertTrue(any('minimum 42' in s['reason'] for s in result.receipt['skipped']))
        self.assertEqual(len(self.replay(result).teams[0].slots), 42)

    def test_extra_player_without_free_slot_and_with_safe_free_slot(self):
        rows = league_sample()
        extra = list(rows[0]); extra[0:2] = ['Free', 'Last00']; extra[10] = 0
        extra[7] = extra[7].replace(year=1999)
        source = signed(synthetic_body(rows + [tuple(extra)]))
        result = importer.compare(self.disc, source)
        self.assertEqual(result.receipt['unmatched'], 1)
        self.assertIn('no eligible free player slot', result.receipt['skipped'][0]['reason'])
        # An explicitly empty NFL pool slot, not a free agent or draft prospect.
        blank = list(rows[0]); blank[0:2] = ['', '']; blank[10] = None
        disc = rr.load_body(synthetic_body(rows + [tuple(blank)]))
        p = disc.players[-1]
        disc.free_agents.remove(p.offset)
        for field in ('pbp_id', 'photo_id', 'history_pointer', 'star_tag'):
            p.record.set(field, 0)
        disc._reindex_membership()
        self.disc = rr.load_body(disc.to_body())
        result = importer.compare(self.disc, source)
        self.assertEqual(result.receipt['added'], 1)
        self.assertEqual(result.receipt['unmatched'], 0)
        self.assertEqual(self.replay(result).players[-1].first, 'Free')
        self.assertEqual(self.replay(result).players[-1].teams, [0])

    def test_direct_file_zip_directory_and_large_wrong_file_are_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            path = save_files(root / 'save', self.save)
            a = importer.from_file(self.disc, path)
            b = importer.from_file(self.disc, path.parent)
            self.assertEqual(a.edits, b.edits)
            archive = root / 'save.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                for p in path.parent.iterdir(): z.write(p, f'53450030/roster/{p.name}')
            self.assertEqual(importer.from_file(self.disc, archive).edits, a.edits)
            large = root / 'wrong.iso'
            with large.open('wb') as f: f.truncate(importer.MAX_SAVE_BYTES + 1)
            with self.assertRaisesRegex(importer.SaveToDiscError, '32 MiB'):
                importer.load_save(large)
            (path.parent / 'EXTRA').write_bytes(bytes(20))
            with self.assertRaisesRegex(rr.RosterRecordError, 'EXTRA does not match'):
                importer.from_file(self.disc, path)

    def test_cli_creates_normal_edits_and_receipt_and_refuses_existing_outputs(self):
        import contextlib
        import io
        import json
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            fixture = image_fixture(root, self.disc.to_body())
            self.save.players[0].record.set('speed', 98)
            source = save_files(root / 'save', self.save)
            output = root / 'roster_edits.json'
            args = ['--disc', str(fixture.path), '--save', str(source), '--output', str(output)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(importer.main(args), 0)
            self.assertEqual(rr.read_edits(output)['schema'], rr.EDITS_SCHEMA)
            receipt = json.loads(output.with_suffix('.receipt.json').read_text())
            self.assertEqual(receipt['edits_sha256'], hashlib.sha256(output.read_bytes()).hexdigest())
            with self.assertRaisesRegex(importer.SaveToDiscError, 'already exists'):
                importer.main(args)

    def test_capability_handoff_is_schema_valid(self):
        import json
        from mod_editor.capabilities.validate_registry import validate_data
        registry = json.loads((ROOT / 'mod_editor/capabilities/registry.v1.json').read_text())
        row = json.loads((ROOT / 'docs/mod_editor/nfl2k5_roster_save_to_disc_capability.json').read_text())
        registry['capabilities'] = [r for r in registry['capabilities'] if r['id'] != row['id']] + [row]
        registry['capabilities'].sort(key=lambda r: r['id'])
        validate_data(registry, check_files=False)
        self.assertTrue(row['backend']['command'].startswith('python3 -m '))
        self.assertTrue(row['validation_command'].startswith('python3 -m '))

    def test_franchise_arena_is_carried_and_season_bytes_are_untouched(self):
        from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise
        from mod_editor.core import nfl2k5_franchise_save as fs
        self.disc = rr.load_body(synthetic_body())
        self.save = signed(synthetic_franchise(year_field=22), runtime=False)
        self.save.players[0].record.set('contract_value', 876)
        before = self.save.to_body()
        result = importer.compare(self.disc, self.save)
        self.assertEqual(result.receipt['source_kind'], 'franchise save')
        self.assertIn('roster arena', result.receipt['source_note'])
        self.assertEqual(self.replay(result).players[0].record.get('contract_value'), 876)
        self.assertEqual(self.save.to_body()[fs.ARENA_END:], before[fs.ARENA_END:])

    def test_franchise_ir_owner_is_reported_and_never_orphans_disc_player(self):
        from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise
        from mod_editor.core import nfl2k5_franchise_save as fs
        self.disc = rr.load_body(synthetic_body())
        franchise = fs.FranchiseSave(synthetic_franchise())
        franchise.place_on_injured_reserve(0, 1)
        self.save = signed(franchise.to_bytes(), runtime=False)
        result = importer.compare(self.disc, self.save)
        target = self.replay(result)
        self.assertEqual(target.players[1].teams, [0])
        self.assertEqual(target.players[1].record.get('injured_reserve'), 0)
        self.assertTrue(any('Injured-reserve ownership' in s['reason'] for s in result.receipt['skipped']))

    def test_reserve_moves_are_reported_and_target_ownership_survives(self):
        self.save.demote_active(0, 0)
        self.save.players[0].record.set('speed', 96)
        result = importer.compare(self.disc, self.save)
        self.assertTrue(any(s['field'] == 'membership' and 'Reserve ownership' in s['reason']
                            for s in result.receipt['skipped']))
        target = self.replay(result)
        self.assertEqual(target.players[0].teams, [0])
        self.assertEqual(target.reserves[0], ())
        self.assertEqual(target.players[0].record.get('speed'), 96)
        original_asset = self.save.teams[0].asset_id
        self.save.teams[0].asset_id = 999
        missing_team = importer.compare(self.disc, self.save)
        self.assertTrue(any(s['save']['index'] == 0 and 'Reserve ownership' in s['reason']
                            for s in missing_team.receipt['skipped']))
        self.save.teams[0].asset_id = original_asset
        # Existing reserves can receive attributes, with no ownership conversion.
        from mod_editor.core import nfl2k5_practice_squad as ps
        body = bytearray(self.disc.to_body())
        team = self.disc.teams[0]
        body[team.offset:team.offset+rr.TEAM_SIZE] = ps.repack_team(
            bytes(body[team.offset:team.offset+rr.TEAM_SIZE]), range(1, 44), [0],
            team_offset=team.offset, player_pool_offset=self.disc.primary_table,
            player_count=len(self.disc.by_pool('primary')), mark=True)
        self.disc = rr.load_body(bytes(body))
        result = importer.compare(self.disc, self.save)
        target = self.replay(result)
        self.assertEqual(target.reserves[0], (0,))
        self.assertEqual(target.players[0].teams, [])
        self.assertFalse(any(s['field'] == 'membership' for s in result.receipt['skipped']))
        # The shared replay refuses a forged move that would give a reserve a second owner.
        changed, receipt = rr.apply_body(self.disc.to_body(), {
            'schema': rr.EDITS_SCHEMA, 'edits': [], 'moves': [
                {'pool': 'primary', 'index': 0, 'to_teams': [{'team_index': 1}], 'free_agent': False}]}, scheme='retail')
        self.assertEqual(changed, self.disc.to_body())
        self.assertIn('reserve moves', receipt['log'][0])

    def test_new_player_name_failure_rolls_back_slot_and_continues_other_edits(self):
        rows = league_sample()
        blank = list(rows[0]); blank[:2] = ['', '']; blank[10] = None
        d = rr.load_body(synthetic_body(rows + [tuple(blank)]))
        slot = d.players[-1]
        d.free_agents.remove(slot.offset)
        for field in ('pbp_id', 'photo_id', 'history_pointer', 'star_tag'):
            slot.record.set(field, 0)
        d._reindex_membership()
        self.disc = rr.load_body(d.to_body())
        extra = list(rows[0]); extra[:2] = ['Free', 'AnImpossiblyLongLastName']; extra[10] = 0
        extra[7] = extra[7].replace(year=1999)
        self.save = signed(synthetic_body(rows + [tuple(extra)]))
        self.save.players[2].record.set('speed', 97)
        result = importer.compare(self.disc, self.save)
        self.assertEqual((result.receipt['added'], result.receipt['unmatched']), (0, 1))
        target = self.replay(result)
        self.assertEqual(target.players[-1].first, '')
        self.assertEqual(target.players[-1].last, '')
        self.assertEqual(target.players[2].record.get('speed'), 97)

    @unittest.skipUnless(HAVE_RETAIL, 'retail extraction absent; v18/v1 arena migration requires NFL table')
    def test_grown_disc_and_save_preserve_overflow_and_import_fields(self):
        from mod_editor.core import nfl2k5_roster_arena as arena
        resource = synthetic_resource(retail_body())
        grown, _ = arena.migrate(resource)
        self.disc = rr.load_body(grown[rr.RESOURCE_HEADER_SIZE:])
        legacy_save = synthetic_save_v0(retail_body())
        grown_save, _ = arena.migrate(legacy_save)
        self.save = signed(grown_save, runtime=False)
        self.save.players[0].record.set('speed', 97)
        result = importer.compare(self.disc, self.save)
        target = self.replay(result)
        self.assertEqual((target.version, self.save.version), (18, 1))
        self.assertEqual(target.overflow, self.disc.overflow)
        self.assertEqual(target.players[0].record.get('speed'), 97)

    @unittest.skipUnless(HAVE_RETAIL, 'retail extraction absent; bounded real ROST comparison unavailable')
    def test_retail_roster_and_reclassified_disc_round_trip(self):
        for body, scheme in ((retail_body(), 'retail'), (reclassified_retail_body(), 'one_pool')):
            disc = rr.load_body(body, scheme=scheme)
            source = signed(body)
            source.set_scheme(scheme)
            source.players[0].record.set('speed', 98)
            result = importer.compare(disc, source)
            target, receipt = rr.apply_body(body, result.edits, scheme=scheme)
            self.assertEqual(receipt['log'], [])
            self.assertEqual(rr.load_body(target).players[0].record.get('speed'), 98)


if __name__ == '__main__':
    unittest.main()
