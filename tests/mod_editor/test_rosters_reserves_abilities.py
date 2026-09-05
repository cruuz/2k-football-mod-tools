"""Portable host storage/transactions. No guest execution or external writes."""
from pathlib import Path
import csv
import io
import os
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_save_rost as codec
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_player_tags as tags
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body, synthetic_save_v0, league_body
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise, F0, F1


def league_save(active=53):
    return synthetic_save_v0(league_body(active), suffix=synthetic_franchise()[fs.ARENA_END:])


def document(payload=None):
    return rr.RosterDocument(payload or synthetic_franchise(), base=fs.ARENA_PREAMBLE)


class AbilityTests(unittest.TestCase):
    def test_masks_keep_locks_star_future_flags_and_codec_keys(self):
        for low in range(256):
            for high in (0, 1, 0x1f, 0xa5, 0xff):
                raw = bytes(82) + bytes((low, high))
                record = rr.PlayerRecord.decode(raw)
                self.assertEqual(record.encode(), raw)
                self.assertEqual(set(record.values), set(rr.decode_record(raw)))
                for name, (field, bit) in rr.ABILITY_BITS.items():
                    byte = 82 if field == 'unknown_52' else 83
                    mask = bit if byte == 82 else bit << 1
                    for value in (True, False):
                        changed = rr.PlayerRecord.decode(raw)
                        changed.set_ability(name, value)
                        expected = bytearray(raw)
                        expected[byte] = expected[byte] | mask if value else expected[byte] & ~mask
                        self.assertEqual(changed.encode(), bytes(expected))
        self.assertEqual(rr.field_coverage(), [8] * 84)

    def test_csv_and_json_round_trips_preserve_neighbor_bits(self):
        doc = document()
        p = doc.players[0]
        p.record.values['unknown_52'] = 0x13
        p.record.values['unknown_53_high'] = 0x70
        p.record.set('star_tag', 1)
        before = doc.to_body()
        csv_text = rr.export_csv(doc)
        self.assertEqual(rr.import_csv(doc, csv_text)['fields'], 0)
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        rows[0]['speedster'], rows[0]['spin'] = '1', '1'
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
        rr.import_csv(doc, out.getvalue())
        self.assertEqual(p.record.values['unknown_52'], 0x33)
        self.assertEqual(p.record.encode()[83], 0xe3)
        self.assertEqual(doc.diff()[0]['changes']['unknown_52'], (0, 0x33))
        self.assertIn('unknown_53_high', doc.diff()[0]['changes'])
        self.assertNotEqual(doc.to_body(), before)
        # Sparse edit replay on a disc keeps the compatibility keys.
        disc = rr.load_body(synthetic_body())
        disc.players[0].record.set_ability('speedster', True)
        disc.players[0].record.set_ability('spin', True)
        edits = rr.edits_document(disc)
        replay, _ = rr.apply_body(synthetic_body(), edits)
        self.assertEqual(replay, disc.to_body())

    def test_save_codec_named_ability_edit_and_tag_status(self):
        save = codec.decode(synthetic_franchise())
        p = save.players[0]
        save.edit_player(p.pool, p.index, {'speedster': 1, 'juke': 1, 'stiff_arm': 1})
        data = save.to_bytes()
        self.assertEqual(data[p.offset+82:p.offset+84], b'\xa0\x10')
        self.assertEqual(codec.decode(data).to_bytes(), data)
        disc = rr.load_body(synthetic_body())
        disc.players[0].record.values['unknown_53_high'] = 0x7f
        self.assertEqual(tags.body_status(disc.to_body()), 'retail')
        disc.players[0].record.set('star_tag', 1)
        self.assertEqual(tags.body_status(disc.to_body()), 'applied')


class LockLayoutTests(unittest.TestCase):
    def test_expanded_bench_is_independent_of_position_stride_and_stays_pinned(self):
        from mod_editor.core import nfl2k5_depth_locks as locks
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        from mod_editor.core import nfl2k5_modern_positions as modern
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        path = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)' / 'default.xbe'
        if not path.is_file():
            self.skipTest('retail default.xbe is absent for the static layout composition check')
        retail = path.read_bytes()
        from mod_editor.core import nfl2k5_position_pools as pools
        phase_one, _ = modern.apply(retail)
        pooled, _ = pools.apply(phase_one)
        expanded, _ = rows.apply(pooled)
        self.assertEqual(modern.layout_stride(expanded), 11)
        patched, _ = locks.apply(expanded)
        self.assertEqual(locks.status(patched), 'applied')
        self.assertEqual(locks.apply(patched)[0], patched)
        # Return instructions and bench callers must still be exact.
        image = XbeImage(expanded)
        damaged = bytearray(expanded)
        section = image.section(rows.BENCH_VA)
        offset = section.raw + rows.BENCH_VA - section.start
        damaged[offset+1] ^= 1
        with self.assertRaisesRegex(locks.DepthLockError, 'bench promotion|depth-chart layout'):
            locks.apply(bytes(damaged))


class SalaryTests(unittest.TestCase):
    def test_native_arithmetic_witnesses(self):
        # Produced from pinned retail E6380/E6040/E6020/E3F10 arithmetic,
        # assembled for the native x64 host with only stack/address adaptation.
        expected = ((1480, 1234, 987), (1727, 1234, 740), (1234, 1234, 1234),
                    (863, 1851, 863), (1604, 617, 1604), (1480, 1480, 1480),
                    (740, 1234, 1727), (987, 1234, 1480))
        for kind, row in enumerate(expected):
            for year, amount in zip((0, 2, 4), row):
                self.assertEqual(ps.contract_base_salary(1234, kind, 5, year, 5), amount)
                self.assertEqual(ps.contract_bonus_salary(1234, 5, 5), 1234)
        self.assertEqual(ps.contract_base_salary(1, 2, 0, 0, 6), 1)  # truncation, not rounding
        self.assertEqual(ps.contract_base_salary(99, 5, 0, 1, 3), 264)
        for bad in ((1, 8, 0, 0, 1), (1, 2, 0, 0, 0), (1, 2, 0, -1, 1)):
            with self.assertRaises(ps.PracticeSquadError):
                ps.contract_base_salary(*bad)

    def test_reserve_salary_excluded_ir_included_and_contract_preserved(self):
        save = fs.FranchiseSave(synthetic_franchise())
        save.place_on_injured_reserve(0, 1)
        p = save.player_offset(0)
        original = save.to_bytes()[p:p+84]
        result = save.demote_active(0, 0)
        remaining = save.player_offset(2)
        ir = save.player_offset(1)
        expected = ps.player_salary(save.to_bytes()[remaining:remaining+84]) + ps.player_salary(save.to_bytes()[ir:ir+84], active=False)
        self.assertEqual(result['salary'], expected)
        self.assertEqual(save.to_bytes()[p+0xa:p+0xc], original[0xa:0xc])
        self.assertEqual(save.to_bytes()[p+0x26:p+0x28], original[0x26:0x28])
        save.promote_reserve(0, 0)
        self.assertEqual(save.team_salary(0), expected + ps.player_salary(original))


class ReserveTests(unittest.TestCase):
    def test_atomic_move_flags_indices_identity_and_undo(self):
        doc = document()
        p = doc.players[1]
        team = doc.teams[0]
        doc.body[team.offset+0x194:team.offset+0x19a] = bytes((0, 1, 2, 0xff, 0x80, 0x7f))
        p.record.values['unknown_25_high'] = 7
        p.record.values['unknown_52'] = 0xff
        p.record.values['unknown_53_high'] = 0x7f
        before = doc.membership_snapshot()
        rank = p.record.values['depth_rank'], p.record.values['depth_side']
        doc.demote_active(0, 1)
        self.assertIs(doc.by_offset[p.offset], p)
        self.assertEqual(doc.reserve_owner, {('primary', 1): 0})
        self.assertNotIn(p.offset, team.slots)
        self.assertEqual(p.group, 'reserve')
        self.assertEqual(p.record.values['unknown_52'], 0xe0)
        self.assertEqual(p.record.values['unknown_25_high'], 0)
        self.assertEqual(doc.to_body()[team.offset+0x194:team.offset+0x19a], bytes((0, 0xff, 1, 0xff, 0x80, 0x7e)))
        self.assertEqual((p.record.values['depth_rank'], p.record.values['depth_side']), rank)
        self.assertEqual(p.record.values['unknown_53_high'], 0x7f)
        with self.assertRaisesRegex(rr.RosterRecordError, 'signed-save copy'):
            rr.edits_document(doc)
        after = doc.to_body()
        doc.restore_membership(before)
        self.assertEqual(doc.to_body(), before['body'])
        doc.adopt_body(after)
        doc.promote_reserve(0, 1)
        self.assertEqual(team.slots[-1], p.offset)
        self.assertEqual(doc.reserve_owner, {})

    def test_limits_53_12_65_and_refusal_bytes(self):
        doc = document(league_save(65))
        for i in range(12):
            doc.demote_active(0, i)
        self.assertEqual((len(doc.teams[0].slots), len(doc.reserves[0])), (53, 12))
        before = doc.to_body()
        for op, index in ((doc.promote_reserve, 0), (doc.demote_active, 12)):
            with self.assertRaises(rr.MembershipRefused):
                op(0, index)
            self.assertEqual(doc.to_body(), before)
        doc.release(doc.players[12], 0, minimum=0)
        self.assertEqual(len(doc.teams[0].slots), 52)
        doc.promote_reserve(0, 0)
        self.assertEqual((len(doc.teams[0].slots), len(doc.reserves[0])), (53, 11))
        doc.demote_active(0, 0)
        self.assertEqual((len(doc.teams[0].slots), len(doc.reserves[0])), (52, 12))
        ps.validate_save(doc.to_body())

    def test_ordinary_moves_ir_and_export_preserve_owners(self):
        doc = document(league_save(44))
        doc.demote_active(0, 0)
        reserved = doc.players[0]
        before = doc.to_body()
        for operation in (lambda: doc.sign(reserved, 1), lambda: doc.transfer(reserved, 1),
                          lambda: doc.release(reserved, 0), lambda: doc.swap(reserved, doc.players[44]),
                          lambda: doc.check_operation(reserved, 'injured_reserve')):
            with self.assertRaises(rr.MembershipRefused): operation()
            self.assertEqual(doc.to_body(), before)
        doc.release(doc.players[1], 0, minimum=0)
        doc.sign(doc.players[1], 1)
        doc.swap(doc.players[2], doc.players[45])
        save = fs.FranchiseSave(doc.to_body())
        save.place_on_injured_reserve(0, 3)
        save.activate_from_injured_reserve(0, 3)
        self.assertEqual(ps.validate_save(save.to_bytes())[0], (0,))
        doc.adopt_body(save.to_bytes())
        self.assertEqual(rr.import_csv(doc, rr.export_csv(doc))['fields'], 0)

    def test_unknown_metadata_duplicate_owners_and_bad_salary_refuse(self):
        payload = synthetic_franchise()
        doc = document(payload)
        bad = bytearray(payload); bad[doc.teams[0].offset + ps.VERSION_OFFSET] = 2
        with self.assertRaisesRegex(rr.RosterRecordError, 'unsupported reserve metadata'): document(bytes(bad))
        # Duplicate active ownership must refuse before any movement.
        bad = bytearray(payload)
        field = doc.teams[1].offset
        struct.pack_into('<i', bad, field, doc.players[0].offset-field+1)
        with self.assertRaisesRegex(ps.PracticeSquadError, 'duplicate owner'):
            ps.reserve_transaction(bytes(bad), 0, 0, promote=False)
        doc.players[1].record.set('contract_type', 15)
        before = doc.to_body()
        with self.assertRaisesRegex(rr.MembershipRefused, 'contract type'):
            doc.demote_active(0, 0)
        self.assertEqual(doc.to_body(), before)

    def test_remap_reads_old_coordinates_and_writes_new_coordinates(self):
        raw = ps.set_reserve_list(bytes(500), [0, 3, 4], team_offset=0x2000,
                                  player_pool_offset=0x1000, player_count=10)
        remapped = ps.remap_reserve_list(raw, {0: 7, 3: None, 4: 0},
            old_team_offset=0x2000, old_player_pool_offset=0x1000,
            team_offset=0x5000, player_pool_offset=0x7000, player_count=10)
        self.assertEqual(ps.reserve_list(remapped, team_offset=0x5000, player_pool_offset=0x7000), (7, 0))
        with self.assertRaisesRegex(ps.PracticeSquadError, 'incomplete'):
            ps.remap_reserve_list(raw, {0: 7, 3: None}, team_offset=0x2000, player_pool_offset=0x1000)

    def test_signed_copy_reopen_and_other_members_unchanged(self):
        payload = synthetic_franchise()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            source = root / 'source'; source.mkdir()
            (source/'SAVEGAME.DAT').write_bytes(payload)
            (source/'EXTRA').write_bytes(rr.sign_save(payload))
            (source/'SaveMeta.xbx').write_bytes(b'metadata')
            doc = rr.load_save(source)
            doc.demote_active(0, 0)
            rr.save_document(doc, root/'copy.zip')
            back = rr.load_save(root/'copy.zip')
            self.assertEqual(back.reserve_owner, {('primary', 0): 0})
            self.assertEqual(back.to_body(), doc.to_body())
            self.assertEqual(back.container.members['SaveMeta.xbx'], b'metadata')
            self.assertEqual((source/'SAVEGAME.DAT').read_bytes(), payload)

    def test_real_v0_fixtures_round_trip_moves(self):
        if not F0.is_file() or not F1.is_file():
            self.skipTest('private hash-pinned f0/f1 franchise fixtures are absent')
        for path in (F0, F1):
            with self.subTest(path=path):
                payload = path.read_bytes()
                doc = document(payload)
                player = doc.team_players(0)[-1]
                doc.demote_active(0, player.index)
                decoded = codec.decode(doc.to_body())
                self.assertEqual(decoded.to_bytes(), doc.to_body())
                self.assertEqual(doc.reserve_owner[player.pool, player.index], 0)
                doc.promote_reserve(0, player.index)
                self.assertEqual(len(doc.to_body()), len(payload))
                self.assertEqual(doc.to_body()[fs.ARENA_END:], payload[fs.ARENA_END:])


if __name__ == '__main__':
    unittest.main()
