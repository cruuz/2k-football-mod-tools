"""Incremental source/ledger invalidation and atomic bulk confirmation."""
from pathlib import Path
import os
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio import playcalling_service as service
from mod_editor.apf_studio.book_content import BookSourceCache
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture


class SourceIdentityTests(unittest.TestCase):
    def test_resource_identity_hashes_only_changed_spans_and_invalidates_replacements(self):
        import apf_outer, apf_inner
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); index = root / '0A'; pack = root / '0B'
            index.write_bytes(b'authored index'); pack.write_bytes(b'bookother')
            entry = NS(name_id=123, size=4, segments=(NS(pack_ordinal=0),))
            archive = NS(entries=(entry,), packs=(NS(path=pack),))
            class Reader:
                def __init__(self, archive): pass
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, entry, offset, size): return pack.read_bytes()[:size]
            cache = BookSourceCache()
            with patch.object(apf_outer, 'parse_archive', return_value=archive), patch.object(apf_inner, 'ArchiveReader', Reader):
                with patch.object(Path, 'read_bytes', autospec=True, side_effect=Path.read_bytes) as read:
                    # Use a separate parser spy; resource hash reads are distinct.
                    from unittest.mock import Mock
                    parser = Mock(side_effect=lambda: pack.read_bytes()[:4].decode())
                    self.assertEqual(cache.resource(index, 123, parser), 'book')
                    calls = read.call_count
                    self.assertEqual(cache.resource(index, 123, parser), 'book')
                    self.assertEqual(read.call_count, calls)
                    stamp = pack.stat()
                    pack.write_bytes(b'bookOTHER')
                    os.utime(pack, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                    self.assertEqual(cache.resource(index, 123, parser), 'book')
                    self.assertEqual(parser.call_count, 1, 'unchanged book span must keep its parse')
                    replacement = root / 'replacement'; replacement.write_bytes(b'EDITOTHER')
                    os.utime(replacement, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                    os.replace(replacement, pack)
                    self.assertEqual(cache.resource(index, 123, parser), 'EDIT')
                    self.assertEqual(parser.call_count, 2)
                    self.assertEqual(cache.resources[123][0][0][:3], (str(pack), 9, stamp.st_mtime_ns))
                    self.assertEqual(cache.resources[123][1], service.digest(b'EDIT'))
                    index.write_bytes(b'another index')
                    cache.resource(index, 123, parser)
                    self.assertEqual(parser.call_count, 3)
                    pack.unlink()
                    with self.assertRaises(FileNotFoundError): cache.token(index)


class WorkflowTests(FacadeFixture):
    def test_confirm_calls_existing_review_with_identical_inputs_for_every_control(self):
        engine = self.facade._playcalling
        requests = [
            dict(kind='ratings', book='O-ManBlock', formation=62, ratings=[1, 2, 3]),
            dict(kind='play_rating', book='O-ManBlock', formation=62, play=10, value=2),
            dict(kind='categories', book='O-ManBlock', formation=62, primary=3, secondary=[3]),
            dict(kind='remove', book='O-ManBlock', formation=62),
            dict(kind='retire', book='O-ManBlock', category=3),
            dict(kind='never_call', book='O-ManBlock', formation=62, never=True, restore_masks=[8]),
            dict(kind='tendency', team=0, value=61),
            dict(kind='audibles', book='O-ManBlock'),
            dict(kind='master_row', category=3, row=6),
            dict(kind='master_roles', category=3, roles=[0]*11),
            dict(kind='situation_masks_enabled', enabled=True),
            dict(kind='situation_mask', book='O-ManBlock', key=8, formation=62, exclude=True),
            self.facade.playcalling_plan('offense', 0, 'O-ManBlock'),
        ]
        for request in requests:
            with self.subTest(kind=request['kind']):
                expected = engine.review(self.facade.session, request)
                with patch.object(engine, 'review', wraps=engine.review) as review:
                    result = self.facade.confirm_playcalling([request])
                self.assertEqual(review.call_count, 1)
                self.assertEqual(review.call_args.args, (self.facade.session, request))
                self.assertEqual(result['reviews'][0]['event'], expected['event'])
                self.assertEqual(result['blockers'], [])
                self.assertEqual(engine.events(self.facade.session), [expected['event']])
                self.facade.undo()

    def test_warm_63_edits_never_reload_or_replay_prior_rows(self):
        engine = self.facade._playcalling
        self.backend.cache_token = lambda session: ('unchanged source identity',)
        with patch.object(self.backend, 'load', wraps=self.backend.load) as load, \
             patch.object(engine, 'apply', wraps=engine.apply) as apply:
            self.facade.playcalling_context()
            for i in range(63):
                request = (dict(kind='ratings', book='O-ManBlock', formation=62, ratings=[i % 8]*3),
                           dict(kind='play_rating', book='O-ManBlock', formation=62, play=10, value=i % 8),
                           dict(kind='audibles', book='O-ManBlock'))[i % 3]
                self.assertEqual(self.facade.confirm_playcalling([request])['staged'], [0])
                self.facade.playcalling_context()
            self.assertEqual(load.call_count, 1)
            self.assertEqual(apply.call_count, 63)
            self.facade.undo(); self.facade.playcalling_context()
            self.assertEqual(apply.call_count, 63, 'Undo must reuse a validated prefix')
        with patch.object(service, 'read_profile', wraps=service.read_profile) as reader:
            for _ in range(3): engine.events(self.facade.session)
            self.assertLessEqual(reader.call_count, 1)

    def test_source_change_revalidates_only_rows_consuming_the_changed_book(self):
        engine = self.facade._playcalling
        token = [1]; self.backend.cache_token = lambda session: token[0]
        requests = [dict(kind='ratings', book=name, formation=62, ratings=[1]*3)
                    for name in ('O-ManBlock', 'USER-o')]
        self.facade.confirm_playcalling(requests)
        original = self.backend.initial.books['O-ManBlock']
        self.backend.initial.books['O-ManBlock'] = self.backend.set_play(original, 62, 10, 5)
        token[0] += 1
        with patch.object(engine, 'apply', wraps=engine.apply) as apply:
            state = engine.state(self.facade.session)
        self.assertEqual(apply.call_count, 1)
        self.assertEqual(apply.call_args.args[1]['book'], 'O-ManBlock')
        self.assertEqual(self.backend.splb.play_rating(state.books['O-ManBlock'], 62, 10), 5)
        self.assertEqual(self.backend.ratings(state.books['USER-o'], 62), (1, 1, 1))

    def test_ledger_tamper_even_with_preserved_size_and_mtime_is_refused(self):
        self.stage(dict(kind='tendency', team=0, value=63))
        self.facade.playcalling_context()
        modification = self.facade.session.modifications[0]
        path = modification.replacement_path; stamp = path.stat()
        path.write_bytes(path.read_bytes().replace(b'63', b'64'))
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        with self.assertRaisesRegex(ValidationError, 'changed after staging'):
            self.facade.playcalling_context()

    def test_removed_formation_references_block_in_both_orders_clean_set_is_one_undo(self):
        remove = dict(kind='remove', book='O-ManBlock', formation=62)
        reference = dict(kind='ratings', book='O-ManBlock', formation=62, ratings=[7]*3)
        clean = [dict(kind='tendency', team=0, value=63), dict(kind='audibles', book='USER-o')]
        for pair in ([remove, reference], [reference, remove]):
            result = self.facade.confirm_playcalling(pair + clean)
            self.assertEqual(result['staged'], [2, 3])
            self.assertEqual([b['index'] for b in result['blockers']], [0, 1])
            for blocker in result['blockers']:
                for key in ('what', 'where', 'why', 'fix'): self.assertTrue(blocker[key])
            self.assertEqual(len(self.facade.session._undo), 1)
            self.assertEqual([e['request'] for e in self.facade._playcalling.events(self.facade.session)], clean)
            self.facade.undo()
            self.assertFalse(self.facade.session.modifications)

    def test_blocked_donor_keeps_dependent_addition_pending(self):
        book = self.backend.initial.books['USER-o']
        self.backend.initial.books['USER-o'] = self.backend.remove(book, 62).book
        requests = [dict(kind='ratings', book='O-ManBlock', formation=62, ratings=[9]*3),
                    dict(kind='add', book='USER-o', donor='O-ManBlock', formation=62)]
        self.assertFalse(self.facade.playcalling_review(requests[1])['refused'])
        result = self.facade.confirm_playcalling(requests)
        self.assertEqual(result['staged'], [])
        self.assertEqual(len(result['blockers']), 2)
        self.assertFalse(self.facade.session.modifications)

    def test_refused_retirement_keeps_its_run_share_pending(self):
        self.backend.holes = True; self.backend.lineup_callers = 'unclassified'
        result = self.facade.confirm_playcalling([
            dict(kind='retire', book='O-ManBlock', category=3),
            dict(kind='tendency', team=0, value=42)])
        self.assertEqual(result['staged'], [])
        self.assertEqual(len(result['blockers']), 2)
        self.assertFalse(self.facade.session.modifications)

    def test_two_individually_valid_removals_cannot_empty_personnel_together(self):
        self.backend.lineup_callers = 'unclassified'
        self.backend.splb.row_coverage = lambda body, master: {i: tuple(
            r.category_index for r in splb.parse_book(body, 0).records if r.populated) for i in range(11)}
        requests = [dict(kind='remove', book='O-ManBlock', formation=f) for f in (62, 63)]
        for r in requests: self.assertFalse(self.facade.playcalling_review(r)['refused'])
        result = self.facade.confirm_playcalling(requests)
        self.assertEqual(result['staged'], [])
        self.assertEqual(len(result['blockers']), 2)
        self.assertIn('no formation for rows', result['blockers'][1]['why'])
        self.assertFalse(self.facade.session.modifications)
        self.assertFalse(self.facade.session.can_undo)

    def test_master_interaction_rechecks_final_coverage(self):
        self.backend.lineup_callers = 'unclassified'
        self.backend.splb.row_coverage = lambda body, master: {0: (3,) if not master or master[0x48 + 3*16] == 3 else ()}
        result = self.facade.confirm_playcalling([
            dict(kind='remove', book='O-ManBlock', formation=62),
            dict(kind='master_row', category=3, row=6)])
        self.assertEqual(result['staged'], [])
        self.assertEqual(len(result['blockers']), 2)
        self.assertIn('Combined edits', result['blockers'][0]['why'])

    def test_reports_all_independent_writer_errors_without_mutating(self):
        requests = [dict(kind='ratings', book='O-ManBlock', formation=62, ratings=[9]*3),
                    dict(kind='master_row', category=3, row=32),
                    dict(kind='tendency', team=0, value=101)]
        result = self.facade.confirm_playcalling(requests)
        self.assertEqual(len(result['blockers']), 3)
        self.assertFalse(self.facade.session.modifications)
        self.assertFalse(self.facade.session.can_undo)

    def test_failed_atomic_write_preserves_ledger_and_undo_then_retry_and_save_reopen(self):
        requests = [dict(kind='ratings', book='O-ManBlock', formation=62, ratings=[5]*3),
                    dict(kind='situation_masks_enabled', enabled=True),
                    dict(kind='situation_mask', book='O-ManBlock', key=8, formation=62, exclude=True)]
        with patch.object(self.facade.session, '_store_payload', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'): self.facade.confirm_playcalling(requests)
        self.assertFalse(self.facade.session.modifications)
        self.assertFalse(self.facade.session.can_undo)
        self.assertEqual(self.facade.confirm_playcalling(requests)['staged'], [0, 1, 2])
        path = self.facade.session.save_project(self.root / 'bulk.apf2k8mod')
        self.facade.undo(); self.facade.session.load_project(path)
        fresh = service.PlayCallingService(self.backend)
        self.assertEqual(fresh.state(self.facade.session), self.facade._playcalling.state(self.facade.session))
        self.assertEqual([e['request'] for e in fresh.events(self.facade.session)], requests)

    def test_changed_source_invalidates_ledger_and_never_reuses_stale_review(self):
        token = [1]; self.backend.cache_token = lambda session: token[0]
        request = dict(kind='ratings', book='O-ManBlock', formation=62, ratings=[1]*3)
        review = self.facade.playcalling_review(request)
        original = self.backend.initial.books['O-ManBlock']
        self.backend.initial.books['O-ManBlock'] = self.backend.set_ratings(original, 62, [6]*3)
        token[0] += 1
        with self.assertRaisesRegex(ValidationError, 'Book or plan changed'):
            self.facade.stage_playcalling(review)
        self.assertFalse(self.facade.session.modifications)
        self.assertEqual(self.facade.confirm_playcalling([request])['staged'], [0])
        self.backend.initial.books['O-ManBlock'] = original; token[0] += 1
        with self.assertRaisesRegex(ValidationError, 'earlier book edit changed'):
            self.facade.playcalling_context()


if __name__ == '__main__': unittest.main()
