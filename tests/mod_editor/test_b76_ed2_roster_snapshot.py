"""Bounded save-to-disc replacement tests; no emulator or disc build."""
import copy
import struct
import unittest

from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_roster_save_to_disc as importer
from tests.mod_editor.test_roster_save_to_disc import signed, league_body


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.body = league_body()
        self.disc = rr.load_body(self.body)
        self.save = signed(self.body)

    def export(self):
        return importer.compare(self.disc, self.save, replace_roster=True)

    def assert_roster(self, target):
        for src, dst in zip(self.save.players, target.players):
            self.assertEqual((src.first, src.last, src.college), (dst.first, dst.last, dst.college))
            for field in importer.CARRIED_FIELDS:
                self.assertEqual(src.record.get(field), dst.record.get(field), (src.index, field))
        key = lambda doc, off: (doc.by_offset[off].pool, doc.by_offset[off].index)
        for src, dst in zip(self.save.teams, target.teams):
            self.assertEqual([key(self.save, o) for o in src.slots], [key(target, o) for o in dst.slots])
        self.assertEqual(self.save.reserves, target.reserves)
        self.assertEqual([key(self.save, o) for o in self.save.free_agents],
                         [key(target, o) for o in target.free_agents])

    def test_attributes_membership_reserves_specialists_and_replay_are_exact(self):
        self.save.swap(self.save.players[0], self.save.players[44])
        self.save.release(self.save.players[1])
        self.save.sign(self.save.players[88], 1, slot=2)
        self.save.demote_active(0, 3)
        self.save.players[7].record.set('speed', 99)
        self.save.set_name(self.save.players[7], 'first', 'New')
        for offset in rr.SPECIAL_TEAM_OFFSETS.values():
            self.save.body[self.save.teams[0].offset + offset] = 2
        before = self.save.to_body()
        result = self.export()
        after, receipt = rr.apply_body(self.body, result.edits)
        self.assert_roster(rr.load_body(after))
        self.assertEqual(self.save.to_body(), before)
        self.assertEqual(self.disc.to_body(), self.body)
        self.assertEqual(receipt['log'], [])
        self.assertEqual(rr.apply_body(after, result.edits)[0], after)
        # No non-roster tables or presentation labels are copied from the save.
        target = rr.load_body(after)
        for team in target.teams:
            for offset in rr.SPECIAL_TEAM_OFFSETS.values():
                self.assertEqual(after[team.offset + offset], self.save.body[self.save.teams[team.index].offset + offset])
            self.assertEqual(after[team.offset + 0x104:team.offset + 0x118],
                             self.body[team.offset + 0x104:team.offset + 0x118])

    def test_replacement_clears_old_occupant_history_but_keeps_disc_star_tags(self):
        history = 0x42000
        struct.pack_into('<I', self.disc.body, rr.OBJ_OFF + 0x40, 1)
        self.disc.set_rel(rr.OBJ_OFF + 0x44, history)
        struct.pack_into('<I', self.disc.body, history, 0x80000000)
        self.disc.players[0].record.values['history_pointer'] = history - self.disc.players[0].offset - 0x2C + 1
        self.disc.players[0].record.set('star_tag', 1)
        self.save.set_name(self.save.players[0], 'first', 'New')
        after, receipt = rr.apply_body(self.disc.to_body(), self.export().edits)
        player = rr.load_body(after).players[0]
        self.assertEqual(player.record.get('history_pointer'), 0)
        self.assertEqual(player.record.get('star_tag'), 1)
        self.assertEqual(receipt['history_links_cleared'], 1)

    def test_capacity_and_invalid_membership_refuse_instead_of_skipping_players(self):
        edits = self.export().edits
        for problem in ('players', 'teams', 'free_agents', 'fields', 'reserve_owner', 'names'):
            changed = copy.deepcopy(edits)
            if problem == 'players':
                changed['edits'].pop()
            elif problem == 'teams':
                changed['teams'].pop()
            elif problem == 'free_agents':
                changed['free_agents'].append(changed['free_agents'][0])
            elif problem == 'fields':
                changed['edits'][0]['fields']['history_pointer'] = 123
            elif problem == 'reserve_owner':
                changed['teams'][1]['reserves'] = [0]
            else:
                for i, entry in enumerate(changed['edits']):
                    entry['first'] = f'LongFirst{i:05d}'
                    entry['last'] = f'LongLast{i:06d}'
            with self.subTest(problem=problem), self.assertRaises(ValueError):
                rr.apply_body(self.body, changed)
        self.assertEqual(self.disc.to_body(), self.body)

    def test_ir_requires_the_save_instead_of_orphaning_ownership(self):
        self.save.players[0].record.set('injured_reserve', 0xEE)
        with self.assertRaisesRegex(importer.SaveToDiscError, 'HDD'):
            self.export()

    def test_position_merge_at_build_keeps_the_target_scheme(self):
        edits = self.export().edits
        edits['edits'][0]['fields']['position'] = 10
        after, _ = rr.apply_body(self.body, edits, scheme='one_pool')
        self.assertEqual(rr.load_body(after).players[0].record.get('position'),
                         rr.replacement_position_code(10, 'one_pool'))


if __name__ == '__main__':
    unittest.main()
