"""APF72-B offline regressions, including the reported retail Shovel sequence."""
from contextlib import ExitStack
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch, PropertyMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import Qt, QCoreApplication, QEvent
from PyQt5.QtWidgets import QApplication, QTableWidget, QMessageBox
from mod_editor.apf_studio.session import ApfSession, SessionError
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.models import ApfSource
from mod_editor.apf_studio.project import WorkspaceStateStore, project_target_identity
from mod_editor.apf_studio.gui import ApfStudioMainWindow
from mod_editor.apf_studio import session as session_module
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor, fill, model_row, view_row
from mod_editor.apf_studio.playbook_membership_qt import ApfPlaybookMembershipPanel
from mod_editor.apf_studio.playbook_package_map_qt import ApfPackageMapPanel
from mod_editor.apf_studio.playbook_route_qt import PlayAssignmentRoutePanel
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body, _parse, relay_candidates
from mod_editor.core.apf2k8_package_map_writer import PackageMapChange, list_apf_formations, swap_te_and_wr
from tests.mod_editor.test_apf_playcalling_editor_facade import FacadeFixture
from tests.mod_editor.test_apf_workspace_recovery import _WindowFacade, _empty_project, SOURCE_SHA256
from tests.mod_editor import test_apf_studio_safety as safety
from tests.mod_editor.test_apf_studio_safety import _source
from mod_editor.apf_studio.build import ApfBuildService, BuildError
from mod_editor.apf_studio.source import EXPECTED_0A_SHA256
from tests.mod_editor.test_apf_playbook_route_gui import _model
from tests.mod_editor.test_apf_splb_tag_reassignment import _book_bytes, OUTER, ONE
from tests.mod_editor.test_apf2k8_playbook_route_writer import _synthetic_master

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / 'extracted/All-Pro Football 2K8 (USA)/0A'


def run_sync(_label, work, done, *_args, **_kwargs):
    done(work(lambda *_: None))
    return True


class QtCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


class SortingTests(QtCase):
    def setUp(self):
        fixture = FacadeFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.facade = fixture.facade
        self.panel = ApfPlayCallingEditor(self.facade, run_sync)
        self.addCleanup(self.panel.deleteLater)

    def test_all_nine_tables_sort_numbers_and_keep_model_rows_on_refill(self):
        tables = self.panel.findChildren(QTableWidget)
        sortable = [widget for widget in tables if widget.isSortingEnabled()]
        self.assertEqual(len(sortable), 9)
        # Block panel callbacks while exercising each shared table with test rows.
        self.panel._updating = True
        for widget in sortable:
            with self.subTest(table=widget.accessibleName()):
                rows = [(str(n), *([str(n)] * (widget.columnCount()-1))) for n in (10, 2, 100, 2)]
                fill(widget, rows)
                widget.sortItems(0, Qt.AscendingOrder)
                self.assertEqual([widget.item(i, 0).text() for i in range(4)], ['2', '2', '10', '100'])
                self.assertEqual([widget.item(i, 0).data(Qt.UserRole+1) for i in range(2)], [1, 3])
                widget.selectRow(view_row(widget, 0))
                fill(widget, rows)
                self.assertEqual(model_row(widget), 0)
                self.assertEqual(widget.horizontalHeader().sortIndicatorOrder(), Qt.AscendingOrder)
                self.assertEqual([widget.item(i, 0).text() for i in range(4)], ['2', '2', '10', '100'])

    def test_sorted_master_and_candidate_actions_keep_their_model_identity(self):
        table = self.panel.master_table
        table.sortItems(0, Qt.DescendingOrder)
        table.selectRow(0)
        expected = int(table.item(0, 0).text())
        self.panel.queue_edits.setChecked(True)
        self.panel.master_row.setValue(9)
        self.panel.stage_master_row()
        self.assertEqual(self.panel._pending[-1]['category'], expected)
        self.panel.candidate_table.sortItems(0, Qt.DescendingOrder)
        self.panel.candidate_table.selectRow(0)
        index = model_row(self.panel.candidate_table)
        expected_form = self.panel._situations[self.panel.situation_picker.currentIndex()]['candidates'][index]['formation']
        self.panel.remove_candidate()
        self.assertEqual(self.panel._pending[-1]['formation'], expected_form)
        self.panel.pending_table.sortItems(0, Qt.DescendingOrder)
        self.panel._render_pending()
        original = model_row(self.panel.pending_table)
        # Clear a known logical row through the button in its sorted display row.
        self.panel.pending_table.cellWidget(view_row(self.panel.pending_table, 0), 3).click()
        self.assertEqual(len(self.panel._pending), 1)
        self.assertEqual(self.panel._pending[0]['formation'], expected_form)


class RecentAndBuildTests(QtCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='b72 a2 paths ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = WorkspaceStateStore(self.root / 'state')
        self.facade = _WindowFacade()
        self.window = ApfStudioMainWindow(self.facade, workspace_store=self.store)
        self.addCleanup(self.window.deleteLater)

    def test_recent_project_cold_start_loads_recorded_source_then_project(self):
        source = self.root / 'recorded APF game'
        source.mkdir()
        other = self.root / 'different game'
        other.mkdir()
        project = _empty_project(self.root / 'project.apf2k8mod')
        self.store.record_source(source, SOURCE_SHA256)
        self.store.record_project(project, source_path=source)
        self.store.record_source(other, SOURCE_SHA256)
        calls = []
        def load_source(path, progress):
            calls.append(('source', path))
            self.facade.source = ApfSource(path, path, path/'0A', SOURCE_SHA256, 0, 'b'*64, 'Fixture')
            self.facade.source_ready = True
            return self.facade._catalog
        def load_project(path, progress):
            calls.append(('project', path))
            self.assertEqual(self.facade.source.selected_path, source)
            self.facade.last_project_identity = project_target_identity(path)
            return 0
        self.facade.load_source = load_source
        self.facade.load_project = load_project
        with patch.object(self.window, '_run_task', side_effect=run_sync), patch.object(self.window, '_run_when_idle', side_effect=lambda callback: callback()):
            self.window._refresh_recent_menus()
            action = self.window._recent_project_menu.actions()[0]
            self.assertTrue(action.isEnabled())
            action.trigger()
        self.assertEqual(calls, [('source', source), ('project', project)])
        self.assertEqual(self.window._active_project_path, project)
        self.assertEqual(self.store.read().project_sources[str(project)], str(source))
        source.rmdir()
        self.facade.source_ready = False
        with patch.object(self.window, '_show_error') as error:
            self.window._request_project_load(project)
        self.assertIn('missing or unavailable', error.call_args.args[0])
        self.assertEqual(len(calls), 2)

    def test_empty_build_folder_does_not_prompt_nonempty_does_and_source_refuses(self):
        output = self.root / 'empty output'
        output.mkdir()
        game = self.root / 'game'
        game.mkdir()
        self.facade.source_ready = True
        self.facade.source = _source(game)
        self.facade.build = lambda dest, progress, **kw: (dest, kw)
        calls = []
        def runner(_owner, _run, _label, operation, _done):
            calls.append(operation(None))
        with patch('mod_editor.apf_studio.gui.QFileDialog.getExistingDirectory', return_value=str(output)), patch('mod_editor.apf_studio.gui.QMessageBox.question', return_value=QMessageBox.Yes) as prompt, patch('mod_editor.apf_studio.ps3_texture_bundle_qt.run_crest_task', side_effect=runner):
            self.window._build_game()
            prompt.assert_not_called()
            self.assertFalse(calls[-1][1]['replace_existing'])
            (output/'keep.txt').write_text('existing')
            self.window._build_game()
            prompt.assert_called_once()
            self.assertTrue(calls[-1][1]['replace_existing'])
            prompt.return_value = QMessageBox.Cancel
            self.window._build_game()
            self.assertEqual(len(calls), 2)
        with patch('mod_editor.apf_studio.gui.QFileDialog.getExistingDirectory', return_value=str(game)), patch('mod_editor.apf_studio.gui.QMessageBox.information') as message:
            self.window._build_game()
            self.assertIn('source game', message.call_args.args[1])

    def test_writer_accepts_empty_folder_and_requires_replacement_for_nonempty(self):
        game = self.root/'game'
        game.mkdir()
        tree = safety.BuildBoundaryTests._tiny_game(game)
        output = self.root/'output'
        output.mkdir()
        service = ApfBuildService(_source(game))
        with ExitStack() as stack:
            for target, value in [('EXPECTED_TREE', tree), ('disc_book_identity_report', NS()), ('sha256_file', EXPECTED_0A_SHA256), ('apf_outer.parse_archive', NS(entries=[]))]:
                if target == 'EXPECTED_TREE':
                    stack.enter_context(patch('mod_editor.apf_studio.build.'+target, value))
                else:
                    stack.enter_context(patch('mod_editor.apf_studio.build.'+target, return_value={} if target == 'disc_book_identity_report' else value))
            stack.enter_context(patch.object(ApfBuildService, '_verify_composed', return_value='9'*64))
            receipt = service.build((), output)
            self.assertEqual(receipt.output_game, output)
            self.assertEqual((output/'0A').read_bytes(), (game/'0A').read_bytes())
            with self.assertRaises(FileExistsError):
                service.build((), output)
            receipt = service.build((), output, replace_existing=True)
            self.assertTrue(receipt.source_unchanged)
            with self.assertRaises(BuildError):
                service.build((), game, replace_existing=True)


class CacheAndPendingTests(QtCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = ApfSource(self.root, self.root, self.root/'0A', 'a'*64, 0, 'b'*64, 'Fixture')
        self.session = ApfSession(self.source, NS(), cache_root=self.root/'cache')
        self.facade = ApfStudioFacade(cache_root=self.root/'cache')
        self.facade.source, self.facade.catalog, self.facade.session = self.source, NS(), self.session
        self.addCleanup(self.facade.close)

    def test_book_cache_keys_edits_source_bytes_and_failed_validation(self):
        book = splb.parse_book(_book_bytes(), OUTER)
        move = splb.MembershipChange(OUTER, ONE, 200, True)
        with patch.object(session_module, 'read_splb_book', return_value=book) as read, patch.object(session_module, 'compile_splb_book', wraps=splb.compile_book) as compile:
            self.session.apply_splb_membership_batch((move,))
            self.session._compile_splb_groups((move,))
            self.assertEqual(read.call_count, 1)
            self.assertEqual(compile.call_count, 1)
            next_move = replace(move, play_index=201)
            self.session.apply_splb_membership_batch((next_move,))
            self.assertEqual(compile.call_count, 2)
            self.session.undo()
            self.session._compile_splb_groups(self.session.staged_splb_changes())
            self.assertEqual(compile.call_count, 3)
            self.session._splb_books[OUTER] = replace(book, body=book.body[:-1] + bytes([book.body[-1] ^ 1]))
            self.session._compile_splb_groups((move,))
            self.assertEqual(compile.call_count, 4)
            with self.assertRaises(Exception):
                self.session._compile_splb_groups((replace(move, play_index=10000),))
            self.assertEqual(self.session.staged_splb_changes(), (move,))

    def test_master_cache_updates_for_edits_undo_and_reload(self):
        body = _synthetic_master()
        with patch.object(session_module, 'read_master_play_body', return_value=body) as read, patch.object(session_module, 'compile_master_play_edits', wraps=session_module.compile_master_play_edits) as compile:
            self.session.replace_play_assignment_route(0, 0, 1, 0)
            first = self.session._master_play_body()
            self.assertEqual(self.session._master_play_body(), first)
            self.assertEqual(compile.call_count, 1)
            self.session.undo()
            self.assertEqual(self.session._master_play_body(), body)
            self.session.replace_play_assignment_route(0, 0, 1, 0)
            self.assertEqual(compile.call_count, 2)
            replacement = ApfSession(self.source, NS(), cache_root=self.root/'reload')
            self.assertEqual(replacement._master_play_body(), body)
            self.assertEqual(read.call_count, 2)

    def test_fine_tune_pending_ticks_do_not_encode_or_compile_and_confirm_once(self):
        book = splb.parse_book(_book_bytes(), OUTER)
        with patch.object(session_module, 'read_splb_book', return_value=book), patch.object(ApfStudioFacade, 'book_choices', new_callable=PropertyMock, return_value={OUTER: book.name}):
            panel = ApfPlaybookMembershipPanel(self.facade, lambda *_: None)
            self.addCleanup(panel.deleteLater)
            panel.run_task = run_sync
            panel._book = book
            panel._plays = [f'Play {i}' for i in range(586)]
            panel._refresh_formations()
            panel.queue_edits.setChecked(True)
            with patch.object(session_module, 'compile_splb_book', side_effect=AssertionError('no compilation during pending ticks')), patch.object(splb.apf_inner, 'encode_h7a_preserving_tokens', side_effect=AssertionError('no encoding')):
                panel.stage_membership(ONE, 200, True)
                panel.stage_membership(ONE, 201, True)
                self.assertEqual(self.session.modified_count, 0)
                self.assertEqual(panel.pending_count(), 1)
                panel._restore_from_project()
                self.assertEqual(len(panel.staged_changes()), 2)
            panel._confirm_pending()
            self.assertEqual(self.session.modified_count, 2)
            self.assertFalse(panel.pending_count())
            self.session.undo()
            self.assertEqual(self.session.modified_count, 0)

    def test_who_lines_up_pending_maps_confirm_together_without_tick_compilation(self):
        from tests.mod_editor.test_apf_package_map_writer import _synthetic_apf_master
        body = _synthetic_apf_master()
        with patch.object(session_module, 'read_master_play_body', return_value=body):
            panel = ApfPackageMapPanel(self.facade, run_sync)
            self.addCleanup(panel.deleteLater)
            panel.queue_edits.setChecked(True)
            with patch.object(session_module, 'compile_master_play_edits', side_effect=AssertionError('pending must not compile')):
                for index, _name, original in list_apf_formations(body)[:2]:
                    panel._set_draft(index, swap_te_and_wr(original))
                panel.set_context()
                self.assertEqual(len(panel.unstaged_maps()), 2)
                self.assertEqual(self.session.modified_count, 0)
            panel.confirm_pending_button.click()
            self.assertEqual(self.session.modified_count, 2)
            self.assertFalse(panel.unstaged_maps())
            self.session.undo()
            self.assertEqual(self.session.modified_count, 0)

    def test_route_pending_is_atomic_and_kept_on_invalid_confirm(self):
        with patch.object(session_module, 'read_master_play_body', return_value=_synthetic_master()):
            panel = PlayAssignmentRoutePanel(self.facade, run_sync)
            self.addCleanup(panel.deleteLater)
            panel.set_model(_model())
            panel.queue_edits.setChecked(True)
            with patch.object(session_module, 'compile_master_play_edits', side_effect=AssertionError('pending must not compile')):
                panel._copy()
                self.assertEqual(self.session.modified_count, 0)
            panel._confirm_pending()
            self.assertEqual(self.session.modified_count, 1)
            self.assertFalse(panel.pending_count())
            self.session.undo()
            with self.assertRaises(SessionError):
                self.facade.confirm_route_pending((('copy', (0, 0, 1, 0)), ('copy', (0, 1, 99, 0))))
            self.assertEqual(self.session.modified_count, 0)


@unittest.skipUnless(INDEX.is_file(), 'Local APF retail fixture unavailable')
class RetailRegressionTests(QtCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.body = read_master_play_body(INDEX)
        cls.inventory = _parse(cls.body)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = ApfSource(INDEX, INDEX.parent, INDEX, 'a'*64, INDEX.stat().st_size, 'b'*64, 'Offline APF')
        self.session = ApfSession(source, NS(), cache_root=self.root)
        self.session._master_play_source_body = self.body

    def test_shovel_ol_copies_relay_and_consumed_slot_use_staged_view(self):
        names = {play['name']: play['index'] for play in self.inventory['plays']}
        strong, lead = names['H Shovel Strong'], names['H Lead Shovel']
        self.assertEqual(len(self.inventory['plays']), 586)
        self.session.replace_play_assignment_route(strong, 0, 0, 0)
        # The second Shovel has become the sole owner of the displaced OL task.
        with self.assertRaisesRegex(SessionError, 'only used on the target play'):
            self.session.replace_play_assignment_route(lead, 0, 0, 0)
        self.session.copy_play_assignment_route_via_relay(lead, 0, 0, 0, strong, 1)
        original_candidates = relay_candidates(self.body, lead, 1, 0, 1)
        self.assertIn((strong, 1), original_candidates)
        current_candidates = self.session.relay_play_assignment_route_candidates(lead, 1, 0, 1)
        self.assertNotIn((strong, 1), current_candidates)
        # It was shared in retail, but it now carries the only surviving chain.
        with self.assertRaisesRegex(SessionError, "relay slot's current route"):
            self.session.copy_play_assignment_route_via_relay(lead, 1, 0, 1, strong, 1)
        self.session.replace_play_assignment_route(lead, 1, 0, 1)
        final = _parse(self.session._master_play_body())
        starts = lambda parsed: {slot['route_node_index'] for play in parsed['plays'] for slot in play['slots']}
        self.assertEqual(starts(final), starts(self.inventory))
        for target in (strong, lead):
            self.assertEqual(final['plays'][target]['slots'][0]['route_node_index'], self.inventory['plays'][0]['slots'][0]['route_node_index'])

    def test_all_three_warm_qt_refreshes_under_100ms(self):
        facade = ApfStudioFacade(cache_root=self.root)
        facade.source, facade.catalog, facade.session = self.session.source, NS(), self.session
        self.addCleanup(facade.close)
        fine = ApfPlaybookMembershipPanel(facade, run_sync)
        maps = ApfPackageMapPanel(facade, run_sync)
        routes = PlayAssignmentRoutePanel(facade, run_sync)
        routes._plays = tuple((p['index'], p['name']) for p in self.inventory['plays'])
        for panel in (fine, maps, routes):
            self.addCleanup(panel.deleteLater)
        self.assertEqual(fine._book.name, 'O-ManBlock')
        self.app.processEvents()  # Finish first-load layout and deferred deletion before warm timing.
        samples = {}
        for name, refresh in [('Fine-tune Plays', fine.set_context), ('Who lines up', maps.refresh), ('Assignment Routes', routes.refresh)]:
            refresh()
            times = []
            with patch.object(session_module, 'read_splb_book', side_effect=AssertionError('warm refresh reread')), patch.object(session_module, 'read_master_play_body', side_effect=AssertionError('warm refresh reread')), patch.object(session_module, 'compile_master_play_edits', side_effect=AssertionError('warm refresh recompiled')):
                for _ in range(5):
                    start = time.perf_counter()
                    refresh()
                    self.app.processEvents()
                    times.append((time.perf_counter()-start)*1000)
            samples[name] = times
            self.assertLess(max(times), 100, (name, times))
        print('B72_QT_REFRESH_MS=' + json.dumps(samples, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
