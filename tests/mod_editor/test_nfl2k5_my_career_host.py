"""Host-only creation identity, picker, Draft Advisory and cut-risk checks."""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career as career
from mod_editor.core import nfl2k5_my_career_prospects as prospects
from mod_editor.core import nfl2k5_my_career_advisory as advisory
from mod_editor.core import nfl2k5_roster_records as roster
from tests.nfl2k5_my_career_fixture import draft_save, TOKEN, XBE
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body, synthetic_save_v0, league_sample


class CreationTests(unittest.TestCase):
    def test_identity_before_tier_all_51_templates_three_bodies_four_tiers(self):
        # Record every native template/body/tier through the actual prepare path.
        for position in range(17):
            source = draft_save(position)
            for variant in range(3):
                for height, weight in ((67, 170), (74, 220), (80, 350)):
                    for tier in range(1, 5):
                        with self.subTest(position=position, variant=variant, height=height, tier=tier):
                            output, setup, receipt = career.prepare(
                                source, first='My', last='Player', position=position, template=variant,
                                height=height, weight=weight, jersey=17, college='Michigan',
                                prospect_tier=tier, token=TOKEN)
                            chosen = roster.PlayerRecord.decode(bytes.fromhex(receipt['record_after']))
                            self.assertEqual(prospects.native_overall(chosen), (74, 70, 64, 59)[tier-1])
                            self.assertEqual(receipt['identity'], dict(height=height, weight=weight, jersey=17, college='Michigan'))
                            self.assertEqual(career.read_setup(setup), bytes.fromhex(setup['state']))
                            career.validate_state(career.read_setup(setup), output)
                            self.assertEqual(len(output), len(source))

    def test_identity_validation_and_no_source_mutation(self):
        source = draft_save()
        digest = hashlib.sha256(source).hexdigest()
        for options in (dict(jersey=-1), dict(jersey=100), dict(jersey=True), dict(height=59),
                        dict(height=85), dict(weight=149), dict(weight=406), dict(college='Missing'),
                        dict(college=True), dict(college=999), dict(height=72.5)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                career.prepare(source, first='My', last='Player', **options)
        self.assertEqual(hashlib.sha256(source).hexdigest(), digest)

    def test_position_lists_and_distinct_prototype_rows(self):
        retail = ('QB', 'HB', 'WR', 'TE', 'EDGE', 'DT', 'OLB', 'ILB', 'FS', 'SS', 'CB')
        pooled = ('QB', 'HB', 'WR', 'TE', 'EDGE', 'DT', 'LB', 'FS', 'SS', 'CB')
        for scheme, expected in (('retail', retail), ('edge', retail), ('one_pool', pooled)):
            self.assertEqual(tuple(row[1] for row in career.position_choices(scheme)), expected)
            for position, _, _ in career.position_choices(scheme):
                labels = prospects.prototypes(position, scheme=scheme)
                templates = career.templates_for(position, scheme=scheme)
                self.assertEqual(len(labels), 4 if position == 0 else 3)
                self.assertEqual(len({variant for _, variant in labels}), len(labels))
                self.assertEqual({label for label, _ in labels}, {t.label for t in templates})
        templates = career.templates_for(0)
        self.assertEqual(len({tuple(sorted(t.ratings().items())) for t in templates}), 4)
        for tier in range(1, 5):
            vectors = []
            for variant in range(4):
                _, _, receipt = career.prepare(draft_save(), first='My', last='Player', template=variant,
                                                prospect_tier=tier, height=80, weight=350, token=TOKEN)
                record = roster.PlayerRecord.decode(bytes.fromhex(receipt['record_after']))
                self.assertEqual(prospects.native_overall(record), prospects.TIERS[tier][1])
                vectors.append(record.encode()[54:82])
            self.assertEqual(len(set(vectors)), 4)


class AdvisoryTests(unittest.TestCase):
    @staticmethod
    def prepared(position=0, scheme='retail'):
        return career.prepare(draft_save(position), first='My', last='Player', position=position,
                              token=TOKEN, scheme=scheme, prospect_tier=1)

    def test_fixed_outputs_no_writes_and_stale_class_refusal(self):
        payload, _, receipt = self.prepared()
        digest = hashlib.sha256(payload).hexdigest()
        kwargs = dict(player_index=receipt['index'], expected_class=receipt['class_fingerprint'])
        result = advisory.estimate(payload, **kwargs)
        self.assertEqual(advisory.estimate(payload, **kwargs), result)
        self.assertEqual([(r['club_index'], r['position_count'], r['target'], r['maximum'], r['shortfall'],
                           r['headroom'], r['projected_position_rank'], r['projected_roster'], r['cut_risk'])
                          for r in result['clubs']],
                         [(2, 0, 2, 4, 2, 4, 1, 1, 'Low'), (0, 1, 2, 4, 1, 3, 1, 4, 'Low'),
                          (1, 1, 2, 4, 1, 3, 1, 4, 'Low')])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)
        changed = bytearray(payload)
        changed[receipt['record_offset'] + 54] += 1
        with self.assertRaisesRegex(ValueError, 'class or roster mode changed'):
            advisory.estimate(bytes(changed), **kwargs)
        with self.assertRaisesRegex(ValueError, 'class or roster mode changed'):
            advisory.estimate(payload, scheme='one_pool', **kwargs)

    def test_native_tables_and_pooled_lb_targets(self):
        payload, _, receipt = self.prepared(11, 'one_pool')
        result = advisory.estimate(payload, player_index=receipt['index'], scheme='one_pool',
                                   expected_class=receipt['class_fingerprint'])
        self.assertTrue(all((r['target'], r['maximum'], r['shortfall']) == (5, 7, 5) for r in result['clubs']))
        self.assertEqual(advisory.roster_tables()[0][10:12], (3, 2))
        self.assertEqual(advisory.roster_tables('one_pool')[0][10:12], (0, 5))

    def test_cut_risk_53_boundary_position_limits_ties_and_refresh(self):
        # The last primary record is MyPlayer; these active fixtures have known
        # counts and deliberately equal ratings, so incumbents win every tie.
        from mod_editor.core import nfl2k5_franchise_save as fs
        suffix = draft_save()[fs.SEASON_BLOCK:]
        for total, peers, expected in ((52, 1, 'Low'), (53, 1, 'Moderate'),
                                       (52, 2, 'Moderate'), (53, 2, 'High'), (52, 4, 'High')):
            sample = league_sample(total)
            payload = synthetic_save_v0(synthetic_body(sample), suffix=suffix)
            doc = roster.RosterDocument(payload, base=roster.find_block_base(payload))
            chosen = doc.players[-1]
            chosen.record.set('position', 0)
            chosen.record.set('player_type', 16)
            for team in doc.teams[:2]:
                for i, offset in enumerate(team.slots):
                    incumbent = doc.by_offset[offset]
                    if i < peers:
                        # Preserve each incumbent's membership and pointers.
                        for field in roster.RATING_BYTE_ORDER:
                            incumbent.record.set(field, chosen.record.get(field))
                        incumbent.record.set('height', chosen.record.get('height'))
                        incumbent.record.set('weight', chosen.record.get('weight'))
                        incumbent.record.set('position', 0)
                    else:
                        incumbent.record.set('position', 3)
            payload = doc.to_body()
            doc = roster.RosterDocument(payload, base=roster.find_block_base(payload))
            fingerprint = advisory.class_fingerprint(doc)
            result = advisory.estimate(payload, player_index=chosen.index, expected_class=fingerprint)
            club = next(r for r in result['clubs'] if r['club_index'] == 0)
            self.assertEqual((club['cut_risk'], club['projected_position_rank'], club['projected_roster']),
                             (expected, peers+1, total+1))
            # An incumbent position change refreshes counts without changing the class.
            doc.by_offset[doc.teams[0].slots[0]].record.set('position', 3)
            updated = advisory.estimate(doc.to_body(), player_index=chosen.index, expected_class=fingerprint)
            club2 = next(r for r in updated['clubs'] if r['club_index'] == 0)
            self.assertEqual(club2['position_count'], peers-1)

    @unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE required')
    def test_read_tables_match_executable_routines(self):
        from mod_editor.core import nfl2k5_position_pools as pools
        payload = XBE.read_bytes()
        self.assertEqual(advisory.roster_tables(xbe=payload), (pools.RETAIL_TARGETS, pools.RETAIL_MAXIMA))
        with self.assertRaisesRegex(ValueError, 'tables differ'):
            advisory.roster_tables('one_pool', xbe=payload)


if __name__ == '__main__':
    unittest.main()
