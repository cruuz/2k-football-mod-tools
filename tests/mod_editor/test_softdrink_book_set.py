"""Modern/classic Build selection, without disc writes or a Qt display."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import mod_build as build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_playbook_pack as packs
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio.session import StudioSession
from mod_editor.studio import project_archive as projects


def host(state=None):
    # Use the real session settings validation/persistence setter, with its
    # manifest writer replaced because this fixture has no indexed game.
    session = StudioSession.__new__(StudioSession)
    session._build_settings = settings.build_settings(state or {})
    session._write_manifest = Mock()
    facade = Nfl2k5StudioFacade.__new__(Nfl2k5StudioFacade)
    facade._lock = threading.RLock()
    facade._session = session
    return facade


class SoftdrinkBookPathsTests(unittest.TestCase):
    def test_order_duplicates_generator_and_giants_name(self):
        paths = build.softdrink_book_paths(team for team in ('NYG', 'KC', 'ARZ', 'KC'))
        self.assertEqual([p.name for p in paths], [
            'softdrink_arz_modern.2k5book', 'softdrink_kc_modern.2k5book',
            'softdrink_giants_modern.2k5book', 'softdrink_arz_defense.2k5book',
            'softdrink_kc_defense.2k5book', 'softdrink_nyg_defense.2k5book'])
        self.assertEqual(paths, build.softdrink_book_paths({'ARZ', 'KC', 'NYG'}))

    def test_all_64_files_exist_and_target_the_expected_team(self):
        paths = build.softdrink_book_paths(packs.TEAM_BOOKS)
        self.assertEqual(len(set(paths)), 64)
        for index, path in enumerate(paths):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
                pack = packs.load_pack(path)
                self.assertEqual(pack.book.resolved_targets(), (packs.TEAM_BOOKS[index % 32],))
                self.assertEqual(pack.schema, packs.OFFENSE_SCHEMA if index < 32 else packs.DEFENSE_SCHEMA)

    def test_empty_and_invalid_keys(self):
        self.assertEqual(build.softdrink_book_paths(()), [])
        for value in ('ARI', 'LV', 'ALL', 'kc', '', None, 12, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build.softdrink_book_paths(['KC', value])


class SoftdrinkBookSetTests(unittest.TestCase):
    def test_subset_all_none_and_read(self):
        facade = host()
        self.assertEqual(facade.project_softdrink_book_set()['classic_count'], 32)
        status = facade.set_softdrink_book_set(iter(['NYG', 'KC']))
        self.assertEqual(status['modern_teams'], ('KC', 'NYG'))
        self.assertEqual(status['modern_count'], 2)
        self.assertEqual(status['classic_count'], 30)
        self.assertEqual(status['per_team']['KC'], 'modern')
        self.assertEqual(status['per_team']['ATL'], 'classic')
        self.assertEqual(facade.project_softdrink_book_set(), status)
        self.assertEqual(facade.set_softdrink_book_set()['modern_count'], 32)
        self.assertEqual(len(facade.project_build_settings()['playbook_packs']), 64)
        self.assertEqual(facade.set_softdrink_book_set([])['classic_count'], 32)
        self.assertEqual(facade.project_build_settings()['playbook_packs'], [])

    def test_non_managed_packs_preserved_in_existing_slots(self):
        old = build.softdrink_book_paths(['ARZ', 'NYG'])
        generic = str(ROOT / 'data/playbooks/softdrink_modern_defense.2k5book')
        original = ['user/first.2k5book', str(old[0]), generic, str(old[1]),
                    'user/middle.2k5book', str(old[2]), str(old[3]), 'user/last.2k5book']
        facade = host({'playbook_packs': original, 'historic_stock_books': True, 'catch_slider': True})
        facade.set_softdrink_book_set(['KC', 'MIN'])
        current = facade.project_build_settings()['playbook_packs']
        new = iter(map(str, build.softdrink_book_paths(['KC', 'MIN'])))
        expected = [next(new) if Path(p).name in {p.name for p in old} else p for p in original]
        self.assertEqual(current, expected)
        self.assertTrue(facade.project_build_settings()['historic_stock_books'])
        self.assertTrue(facade.project_build_settings()['catch_slider'])
        facade.set_softdrink_book_set([])
        self.assertEqual(facade.project_build_settings()['playbook_packs'],
                         ['user/first.2k5book', generic, 'user/middle.2k5book', 'user/last.2k5book'])

    def test_selection_growth_keeps_user_pack_order_and_duplicates(self):
        pair = list(map(str, build.softdrink_book_paths(['KC'])))
        facade = host({'playbook_packs': ['own.2k5book', pair[0], 'own.2k5book', pair[1], 'last.2k5book']})
        facade.set_softdrink_book_set()
        paths = facade.project_build_settings()['playbook_packs']
        managed = {p.name for p in build.softdrink_book_paths(packs.TEAM_BOOKS)}
        self.assertEqual([p for p in paths if Path(p).name not in managed],
                         ['own.2k5book', 'own.2k5book', 'last.2k5book'])
        self.assertEqual([p for p in paths if Path(p).name in managed],
                         list(map(str, build.softdrink_book_paths(packs.TEAM_BOOKS))))

    def test_idempotence_does_not_write_manifest_again(self):
        facade = host()
        status = facade.set_softdrink_book_set(['KC', 'NYG'])
        facade._session._write_manifest.reset_mock()
        self.assertEqual(facade.set_softdrink_book_set(['NYG', 'KC', 'KC']), status)
        facade._session._write_manifest.assert_not_called()

    def test_invalid_selection_leaves_project_unchanged(self):
        facade = host({'playbook_packs': ['own.2k5book']})
        before = facade.project_build_settings()
        with self.assertRaises(ValueError):
            facade.set_softdrink_book_set(['KC', 'ALIEN'])
        self.assertEqual(facade.project_build_settings(), before)
        facade._session._write_manifest.assert_not_called()

    def test_partial_pairs_reported_and_repaired(self):
        pair = build.softdrink_book_paths(['NYG'])
        facade = host({'playbook_packs': [str(pair[1])]})
        status = facade.project_softdrink_book_set()
        self.assertEqual(status['incomplete_teams'], ('NYG',))
        self.assertEqual(status['per_team']['NYG'], 'incomplete')
        self.assertEqual(status['classic_count'], 31)
        self.assertEqual(facade.set_softdrink_book_set(['NYG'])['incomplete_teams'], ())
        self.assertEqual(facade.project_build_settings()['playbook_packs'], list(map(str, pair)))

    def test_relative_pack_names_are_recognized_generic_names_preserved(self):
        facade = host({'playbook_packs': ['data/playbooks/softdrink_giants_modern.2k5book',
                                        'data/playbooks/softdrink_nyg_defense.2k5book',
                                        'softdrink_option.2k5book']})
        self.assertEqual(facade.project_softdrink_book_set()['modern_teams'], ('NYG',))
        facade.set_softdrink_book_set([])
        self.assertEqual(facade.project_build_settings()['playbook_packs'], ['softdrink_option.2k5book'])

    def test_project_archive_and_build_plan_round_trip(self):
        facade = host({'playbook_packs': ['own.2k5book'], 'historic_stock_books': True})
        expected = facade.set_softdrink_book_set(['ARZ', 'KC', 'NYG'])
        state = facade.project_build_settings()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / 'books.2k5mod'
            projects.save_project_archive(catalog=None, asset_io=None, edits=(), destination=path,
                                          build_settings=state)
            loaded = projects.load_project_archive(source=path, catalog=None, asset_io=None,
                                                   private_root=path.parent)
            try:
                restored = host(loaded.build_settings)
                self.assertEqual(restored.project_softdrink_book_set(), expected)
                self.assertEqual(restored.project_build_settings(), state)
                plan = settings.to_plan(loaded.build_settings, 'source', 'target')
                self.assertEqual(list(plan.playbook_packs), state['playbook_packs'])
                self.assertTrue(plan.historic_stock_books)
            finally:
                loaded.cleanup()


class SoftdrinkPlanningTests(unittest.TestCase):
    def test_all_and_mixed_subset_partition_without_build(self):
        for teams in (packs.TEAM_BOOKS, ('ARZ', 'KC', 'NYG', 'WAS'), ()):
            with self.subTest(teams=teams):
                paths = build.softdrink_book_paths(teams)
                offense, option, defense, community = build.plan_playbook_packs(iter(paths))
                self.assertEqual(offense, paths[:len(teams)])
                self.assertEqual(defense, paths[len(teams):])
                self.assertEqual(option, [])
                self.assertEqual(community, [])

    def test_planner_still_refuses_overlapping_offense(self):
        pack = packs.load_pack(ROOT / 'data/playbooks/modern_gun_core.2k5book')
        pack = replace(pack, book=replace(pack.book, targets=('KC',)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'other.2k5book'
            packs.save_pack(pack, path)
            with self.assertRaisesRegex(ValueError, 'complete offense owns'):
                build.plan_playbook_packs([*build.softdrink_book_paths(['KC']), path])


if __name__ == '__main__':
    unittest.main()
