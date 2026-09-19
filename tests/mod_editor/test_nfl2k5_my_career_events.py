"""Offline event boundaries, journal replay and atomic project persistence."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_events as events
from mod_editor.core import nfl2k5_roster_records as roster


def player():
    record = roster.PlayerRecord.decode(bytes(84))
    roster.apply_template(record, roster.templates_for_position(0)[0])
    record.set('position', 0)
    record.set('height', 74)
    record.set('weight', 220)
    return record


class BandTests(unittest.TestCase):
    def test_tables_match_the_proposal(self):
        self.assertEqual(events.SENIOR_PASS_BANDS, ((200, 1), (300, 2), (400, 3)))
        self.assertEqual(events.SENIOR_RUSH_BANDS, ((50, 1), (75, 2), (100, 3)))
        self.assertEqual(events.DASH_BANDS, ((449, 5), (454, 4), (459, 3), (469, 2), (482, 1)))
        self.assertEqual(events.SKELETON_YARDS_BANDS, ((100, 1), (150, 2), (200, 3)))
        self.assertEqual(events.SKELETON_COMPLETION_BANDS, ((60, 1), (65, 2), (70, 3)))
        endpoints = ((434, 435), (436, 437), (438, 439), (440, 441), (442, 443), (444, 446),
                     (447, 449), (450, 452), (453, 454), (455, 457), (458, 459), (460, 461),
                     (462, 463), (464, 466), (467, 468), (469, 472), (473, 474), (475, 476),
                     (477, 478), (479, 480), (481, 482))
        self.assertEqual(events.MAX_SPEED_CHART, tuple((lo, hi, 95-i) for i, (lo, hi) in enumerate(endpoints)))

    def test_every_yard_boundary_and_off_by_ones(self):
        for key, bands, score in (
            ('senior_pass', events.SENIOR_PASS_BANDS, lambda n: events.senior_bowl_points(n, 0)),
            ('senior_rush', events.SENIOR_RUSH_BANDS, lambda n: events.senior_bowl_points(0, n)),
            ('skeleton_yards', events.SKELETON_YARDS_BANDS,
             lambda n: events.pre_draft_points([5, 6], n, 0)['credits']),
        ):
            for boundary, points in bands:
                for delta, expected in ((-1, points-1), (0, points), (1, points)):
                    with self.subTest(key=key, boundary=boundary, delta=delta):
                        self.assertEqual(score(boundary+delta)[key], expected)
            self.assertEqual(score(-100)[key], 0)
            self.assertEqual(score(10000)[key], 3)

    def test_completion_thresholds_fractional_gaps_and_caps(self):
        for boundary, points in events.SKELETON_COMPLETION_BANDS:
            for delta, expected in ((-1, points-1), (0, points), (1, points)):
                self.assertEqual(events.pre_draft_points([5, 5], 0, boundary+delta)
                                 ['credits']['skeleton_completion'], expected)
            self.assertEqual(events.pre_draft_points([5, 5], 0, Decimal(boundary)-Decimal('.001'))
                             ['credits']['skeleton_completion'], points-1)
        self.assertEqual(sum(events.senior_bowl_points(9999, 9999).values()), 6)
        self.assertEqual(sum(events.pre_draft_points([4, 4], 9999, 100)['credits'].values()), 11)

    def test_dash_bands_all_boundaries_and_neighbors(self):
        bands = ((0, 449, 5), (450, 454, 4), (455, 459, 3), (460, 469, 2), (470, 482, 1))
        for lo, hi, points in bands:
            for hundredths in {max(1, lo-1), max(1, lo), max(1, lo+1), hi-1, hi, hi+1}:
                expected = next((p for a, b, p in bands if a <= hundredths <= b), 0)
                self.assertEqual(events.dash_points(Decimal(hundredths)/100), expected)

    def test_full_speed_chart_roundtrip_gaps_ties_and_outside(self):
        for lo, hi, speed in events.MAX_SPEED_CHART:
            self.assertEqual(events.speed_interval(speed), (Decimal(lo)/100, Decimal(hi)/100))
            for hundredths in range(lo, hi+1):
                self.assertEqual(events.max_speed(Decimal(hundredths)/100), speed)
            self.assertEqual(events.max_speed(Decimal(lo-1)/100), min(95, speed+1))
            self.assertEqual(events.max_speed(Decimal(hi+1)/100), max(75, speed-1))
            self.assertEqual(events.max_speed(Decimal(hi)/100 + Decimal('.0049')), speed)
            self.assertEqual(events.max_speed(Decimal(hi)/100 + Decimal('.005')), max(75, speed-1))
        self.assertEqual(events.max_speed('3.99'), 95)
        self.assertEqual(events.max_speed('9.99'), 75)
        self.assertEqual(events.dash_points('4.495'), 4)
        self.assertEqual(events.dash_points('4.494999'), 5)
        tied = events.pre_draft_points(['4.354', '4.351'], 0, 0)
        self.assertEqual((tied['best_attempt'], tied['speed_cap']), (1, 95))
        self.assertEqual(events.pre_draft_points([5, 4.4], 0, 0)['best_attempt'], 2)

    def test_invalid_measurements_are_refused(self):
        for value in (0, -1, True, None, 'no', float('nan'), float('inf'), '3600.01'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                events.max_speed(value)
        for value in (-1, 101, True, 'NaN'):
            with self.assertRaises(ValueError): events.pre_draft_points([4, 5], 100, value)
        for value in ([], [4], [4, 5, 6]):
            with self.assertRaises(ValueError): events.pre_draft_points(value, 100, 70)
        for value in (True, 200.5, '200'):
            with self.assertRaises(ValueError): events.senior_bowl_points(value, 50)
        for value in (74, 96, True):
            with self.assertRaises(ValueError): events.speed_interval(value)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.record = player()
        self.ledger = events.new_ledger(self.record)
        events.earn(self.ledger, event='senior_bowl', pass_yards=400, rush_yards=100)
        events.earn(self.ledger, event='pre_draft', attempts=[4.4, 4.5], pass_yards=200, completion_percent=70)

    def test_earn_spend_save_reload_duplicate_fails_and_deterministic(self):
        # 4.40 earns five dash points. All 17 points can be spent exactly once.
        purchases = {'senior_pass': {'pass_accuracy': 3}, 'senior_rush': {'agility': 3},
                     'dash': {'speed': 5}, 'skeleton_yards': {'pass_arm_strength': 3},
                     'skeleton_completion': {'consistency': 3}}
        self.assertEqual(events.replay(self.ledger)[1]['earned'], 17)
        before = self.record.encode()
        stale = deepcopy(self.ledger)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'MyCareer events.json'
            events.save_project(path, self.record, self.ledger)
            totals = events.apply_earned(self.record, self.ledger, purchases, transaction_id='all-points')
            self.assertEqual((totals['earned'], totals['spent'], totals['available']), (17, 17, 0))
            events.save_project(path, self.record, self.ledger)
            serialized = path.read_bytes()
            record, ledger = events.load_project(path)
            with self.assertRaisesRegex(ValueError, 'already spent'):
                events.apply_earned(record, ledger, purchases, transaction_id='all-points')
            with self.assertRaisesRegex(ValueError, 'exceeds the points'):
                events.apply_earned(record, ledger, {'dash': {'speed': 1}}, transaction_id='new')
            with self.assertRaisesRegex(ValueError, 'newer or different'):
                events.save_project(path, roster.PlayerRecord.decode(before), stale)
            self.assertEqual(path.read_bytes(), serialized)
            events.save_project(path, record, ledger)
            self.assertEqual(path.read_bytes(), serialized)
            self.assertEqual(events.project_bytes(record, ledger), serialized)
            self.assertEqual(record.encode(), self.record.encode())
            self.assertEqual(ledger, self.ledger)

    def test_atomic_rejections_no_mint_or_style_purchase(self):
        initial = deepcopy(self.ledger), self.record.encode()
        for purchases in ({'senior_pass': {'speed': 1}}, {'dash': {'scramble': 1}},
                          {'dash': {'speed': -1}}, {'dash': {'speed': True}},
                          {'dash': {'speed': 6}}, {'senior_pass': {'pass_accuracy': 1}, 'dash': {'speed': 6}}, {}):
            with self.subTest(purchases=purchases), self.assertRaises(ValueError):
                events.apply_earned(self.record, self.ledger, purchases, transaction_id='invalid')
            self.assertEqual((self.ledger, self.record.encode()), initial)
        for event, result in (('senior_bowl', dict(pass_yards=9999, rush_yards=9999)),
                              ('pre_draft', dict(attempts=[4, 4], pass_yards=9999, completion_percent=100))):
            with self.assertRaisesRegex(ValueError, 'already recorded'):
                events.earn(self.ledger, event=event, **result)
        altered = deepcopy(self.ledger)
        altered['earned'] = 1000
        with self.assertRaises(ValueError): events.replay(altered)
        altered = deepcopy(self.ledger)
        altered['entries'].append({'kind': 'spend', 'id': 'x', 'purchases': {'dash': {'speed': 6}}})
        with self.assertRaises(ValueError): events.replay(altered)
        fresh = events.new_ledger(self.record)
        with self.assertRaises(ValueError):
            events.apply_earned(self.record, fresh, {'dash': {'speed': 1}}, transaction_id='free')

    def test_every_attribute_permission_and_existing_position_cap(self):
        from mod_editor.core import nfl2k5_my_career_progression as progression
        fields = [key for _, key, _ in progression.FIELDS]
        for position in range(17):
            for bucket, allowed in events.PERMISSIONS.items():
                for field in allowed:
                    cap = progression.CAPS[position][fields.index(field)]
                    if field == 'speed': cap = min(cap, 80)
                    record = player()
                    record.set('position', position)
                    record.set(field, cap-1)
                    ledger = events.new_ledger(record)
                    events.earn(ledger, event='senior_bowl', pass_yards=400, rush_yards=100)
                    events.earn(ledger, event='pre_draft', attempts=['4.70', '4.80'], pass_yards=200, completion_percent=70)
                    with self.subTest(position=position, bucket=bucket, field=field):
                        events.apply_earned(record, ledger, {bucket: {field: 1}}, transaction_id='cap')
                        self.assertEqual(record.get(field), cap)
                        with self.assertRaises(ValueError):
                            events.apply_earned(record, ledger, {bucket: {field: 1}}, transaction_id='over')
                        self.assertEqual(record.get(field), cap)

    def test_above_cap_and_changed_record_never_lowered(self):
        record = player()
        record.set('speed', 98)
        ledger = events.new_ledger(record)
        events.earn(ledger, event='pre_draft', attempts=[4.8, 4.9], pass_yards=0, completion_percent=0)
        with self.assertRaisesRegex(ValueError, 'cap'):
            events.apply_earned(record, ledger, {'dash': {'speed': 1}}, transaction_id='x')
        self.assertEqual(record.get('speed'), 98)
        record.set('height', 75)
        with self.assertRaisesRegex(ValueError, 'changed since'):
            events.apply_earned(record, ledger, {'dash': {'agility': 1}}, transaction_id='x')
        self.assertEqual(events.replay(ledger)[1]['spent'], 0)

    def test_project_load_replays_and_atomic_write_failures_keep_previous_file(self):
        import json
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'events.json'
            events.save_project(path, self.record, self.ledger)
            before = path.read_bytes()
            events.apply_earned(self.record, self.ledger, {'dash': {'speed': 1}}, transaction_id='one')
            with patch.object(events.os, 'replace', side_effect=OSError('injected replace failure')):
                with self.assertRaises(OSError): events.save_project(path, self.record, self.ledger)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            lock = path.with_name(path.name+'.lock')
            lock.write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'being saved'):
                events.save_project(path, self.record, self.ledger)
            self.assertEqual(path.read_bytes(), before)
            lock.unlink()
            bad = deepcopy(self.ledger)
            bad['entries'] += [bad['entries'][-1]]
            path.write_text(json.dumps(bad), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'already spent'): events.load_project(path)
            path.write_bytes(b'x'*(events.MAX_PROJECT_BYTES+1))
            with self.assertRaisesRegex(ValueError, '64 KiB'): events.load_project(path)

    def test_undrafted_events_refused_and_spend_id_unique_with_balance_remaining(self):
        ledger = events.new_ledger(self.record, prospect_tier=4)
        with self.assertRaisesRegex(ValueError, 'not invited'):
            events.earn(ledger, event='senior_bowl', pass_yards=400, rush_yards=100)
        events.apply_earned(self.record, self.ledger, {'dash': {'speed': 1}}, transaction_id='once')
        self.assertGreater(events.replay(self.ledger)[1]['available'], 0)
        with self.assertRaisesRegex(ValueError, 'already spent'):
            events.apply_earned(self.record, self.ledger, {'dash': {'speed': 1}}, transaction_id='once')


class StudioProjectTests(unittest.TestCase):
    def test_named_and_recovery_project_reload_cannot_double_spend(self):
        from unittest.mock import patch
        from tests.mod_editor.music_fixtures import MusicDisc, music_session
        from mod_editor.core.errors import ValidationError
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root/'source'
            source.mkdir()
            disc = MusicDisc(source)
            session = music_session(source, disc)[0].session
            record = player()
            ledger = events.new_ledger(record)
            events.earn(ledger, event='senior_bowl', pass_yards=400, rush_yards=100)
            session.set_my_career_events(ledger)
            prior = deepcopy(ledger)
            events.apply_earned(record, ledger, {'senior_pass': {'pass_accuracy': 3}}, transaction_id='first')
            session.set_my_career_events(ledger)
            self.assertTrue(session.has_project_metadata)
            self.assertEqual(session.project_metadata_count, 1)
            detached = session.my_career_events
            detached['entries'].clear()
            self.assertEqual(session.my_career_events, ledger)
            path = root/'career.2k5mod'
            session.save_shareable_project(path)
            destination = root/'reopened'
            destination.mkdir()
            restored = music_session(destination, disc)[0].session
            restored.load_shareable_project(path)
            self.assertEqual(restored.my_career_events, ledger)
            loaded = restored.my_career_events
            loaded_record, totals = events.replay(loaded)
            self.assertEqual((totals['earned'], totals['spent']), (6, 3))
            with self.assertRaisesRegex(ValueError, 'already spent'):
                events.apply_earned(loaded_record, loaded, {'senior_pass': {'pass_accuracy': 3}}, transaction_id='first')
            with self.assertRaisesRegex(ValueError, 'newer or different'):
                restored.set_my_career_events(prior)
            recovery = root/'recovery.2k5mod'
            restored.save_shareable_project(recovery, replace=True, allow_empty=True)
            failed = root/'failed'
            failed.mkdir()
            candidate = music_session(failed, disc)[0].session
            with patch.object(candidate, '_write_manifest', side_effect=OSError('injected import failure')):
                with self.assertRaises(ValidationError): candidate.load_shareable_project(recovery)
            self.assertIsNone(candidate.my_career_events)
            candidate.load_shareable_project(recovery)
            self.assertEqual(candidate.my_career_events, ledger)
            events.apply_earned(loaded_record, loaded, {'senior_rush': {'agility': 1}}, transaction_id='second')
            with patch.object(restored, '_write_manifest', side_effect=OSError('injected save failure')):
                with self.assertRaises(OSError): restored.set_my_career_events(loaded)
            self.assertEqual(restored.my_career_events, ledger)


if __name__ == '__main__':
    unittest.main()
