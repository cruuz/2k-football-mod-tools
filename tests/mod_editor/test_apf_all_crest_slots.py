"""The editor offered 24 crest slots; the game carries 118.

APF ships ``uniform_logo_00.iff`` through ``uniform_logo_117.iff``. Twenty-four
are worn by built-in teams; the other ninety-four are the game's selectable logo
library -- the "swappable options" a modder described cycling through in the
in-game uniform editor, while asking for a way to get their own art onto helmets.

Three independent facts say those ninety-four are real rather than orphans:

* every one has the structure of a team crest -- inner files ``logo_l0`` and
  ``logo_l1``, both 704,736 bytes;
* ``tools/apf_logocache_patch.py`` has always declared ``CATALOG_COUNT = 118``,
  so the runtime-resident aggregate catalogues every slot; and
* the crest writer builds against them today. ``build_patch`` takes
  ``entry_index`` as an ordinary parameter and consults ``PINNED_ENTRIES`` only
  through ``.get()``, so an unpinned slot is permitted rather than refused.

So this was a catalog limit, not a writer limit.

Two things these tests deliberately hold the line on. The slots are resolved from
the user's own archive by CRC32 of the uppercase filename rather than from a
typed list of a hundred-odd entry indices -- the packages are scattered, slot 0
sitting at outer entry 363 while slot 30 is at 1133, and a hand-written table is
a table someone can get wrong. And an unnamed slot is labelled by its index,
never given an invented team name: that it is *writable* is proved, but which
picker position it backs in game is not.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import apf_team_crests as crests  # noqa: E402

_INDEX = _REPO_ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


class SlotContractTests(unittest.TestCase):
    """No game data needed."""

    def test_the_catalog_count_matches_the_logo_cache(self) -> None:
        """The two must agree or one of them is describing a different game."""

        import apf_logocache_patch as cache

        self.assertEqual(crests.CATALOG_SLOT_COUNT, cache.CATALOG_COUNT)
        self.assertEqual(crests.CATALOG_SLOT_COUNT, 118)

    def test_the_team_table_is_unchanged(self) -> None:
        """Existing callers must keep hitting exactly the targets they did."""

        self.assertEqual(len(crests.TEAM_CRESTS), 24)
        self.assertEqual(crests.default_crest().team, "Assassins")
        self.assertEqual(crests.by_team("Americans").asset_index, 30)
        self.assertEqual(crests.by_team("Americans").outer_entry_index, 1133)

    def test_a_team_slot_is_labelled_by_team(self) -> None:
        slot = crests.CrestSlot(30, 1133, crests.by_team("Americans"))
        self.assertTrue(slot.is_team_crest)
        self.assertIn("Americans", slot.label)
        self.assertEqual(slot.package_name, "uniform_logo_30.iff")

    def test_a_library_slot_is_never_given_a_team_name(self) -> None:
        """Writable is proved; which picker position it backs is not."""

        slot = crests.CrestSlot(7, 830, None)
        self.assertFalse(slot.is_team_crest)
        self.assertEqual(slot.label, "Logo slot 07 - uniform_logo_07.iff")
        for row in crests.TEAM_CRESTS:
            self.assertNotIn(row.team, slot.label)


@unittest.skipUnless(_INDEX.is_file(), "extracted APF 0A not present")
class ResolvedSlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.slots = crests.crest_slots(_INDEX)

    def test_every_slot_resolves(self) -> None:
        self.assertEqual(len(self.slots), crests.CATALOG_SLOT_COUNT)
        self.assertEqual(
            [slot.asset_index for slot in self.slots],
            list(range(crests.CATALOG_SLOT_COUNT)),
        )

    def test_the_split_is_twenty_four_teams_and_the_rest_library(self) -> None:
        named = [slot for slot in self.slots if slot.is_team_crest]
        self.assertEqual(len(named), 24)
        self.assertEqual(len(self.slots) - len(named), 94)

    def test_every_built_in_team_still_appears(self) -> None:
        resolved = {slot.team.team for slot in self.slots if slot.team}
        self.assertEqual(resolved, {row.team for row in crests.TEAM_CRESTS})

    def test_resolution_agrees_with_the_team_table_entry_indices(self) -> None:
        """A CRC mismatch would silently point a writer at the wrong package."""

        by_index = {slot.asset_index: slot for slot in self.slots}
        for row in crests.TEAM_CRESTS:
            with self.subTest(team=row.team):
                self.assertEqual(
                    by_index[row.asset_index].outer_entry_index,
                    row.outer_entry_index,
                )

    def test_entry_indices_are_scattered_not_sequential(self) -> None:
        """Guards against anyone 'simplifying' this into index arithmetic."""

        entries = [slot.outer_entry_index for slot in self.slots]
        self.assertNotEqual(entries, sorted(entries))
        self.assertEqual(len(set(entries)), len(entries))

    def test_slot_zero_is_a_library_slot_at_the_measured_entry(self) -> None:
        first = self.slots[0]
        self.assertEqual(first.asset_index, 0)
        self.assertEqual(first.outer_entry_index, 363)
        self.assertFalse(first.is_team_crest)


@unittest.skipUnless(_INDEX.is_file(), "extracted APF 0A not present")
class PickerWidensOnLoadTests(unittest.TestCase):
    """The wiring, not the resolver -- the resolver has its own tests above.

    The failure this guards against is silent: reading the archive path off the
    wrong attribute leaves the picker at twenty-four with no error anywhere.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _panel(self):
        from PyQt5.QtWidgets import QComboBox

        from mod_editor.apf_studio.gui import ApfTeamLogoPanel

        class _Source:
            index_0a = _INDEX

        class _Facade:
            source_ready = True
            source = _Source()

            def __getattr__(self, name):
                return None

        panel = ApfTeamLogoPanel.__new__(ApfTeamLogoPanel)
        panel.slot = QComboBox()
        panel.facade = _Facade()
        panel._slots_populated = False
        for row in crests.TEAM_CRESTS:
            panel.slot.addItem(row.label, row)
        return panel

    def test_it_widens_from_the_teams_to_every_slot(self) -> None:
        panel = self._panel()
        self.assertEqual(panel.slot.count(), len(crests.TEAM_CRESTS))
        panel._populate_slots()
        self.assertEqual(panel.slot.count(), crests.CATALOG_SLOT_COUNT)

    def test_library_slots_are_labelled_by_index(self) -> None:
        panel = self._panel()
        panel._populate_slots()
        labels = [panel.slot.itemText(i) for i in range(panel.slot.count())]
        self.assertEqual(sum(1 for text in labels if "Logo slot" in text), 94)
        self.assertEqual(sum(1 for text in labels if "Logo slot" not in text), 24)

    def test_the_payload_stays_writer_compatible(self) -> None:
        """The build path uses only these two attributes."""

        panel = self._panel()
        panel._populate_slots()
        for index in range(panel.slot.count()):
            data = panel.slot.itemData(index)
            self.assertIsInstance(data.asset_index, int)
            self.assertIsInstance(data.outer_entry_index, int)

    def test_repopulating_is_idempotent(self) -> None:
        """set_context runs on every refresh; it must not multiply the list."""

        panel = self._panel()
        panel._populate_slots()
        count = panel.slot.count()
        panel._populate_slots()
        self.assertEqual(panel.slot.count(), count)

    def test_a_facade_with_no_source_leaves_the_teams_alone(self) -> None:
        from PyQt5.QtWidgets import QComboBox

        from mod_editor.apf_studio.gui import ApfTeamLogoPanel

        class _Empty:
            source_ready = False
            source = None

        panel = ApfTeamLogoPanel.__new__(ApfTeamLogoPanel)
        panel.slot = QComboBox()
        panel.facade = _Empty()
        panel._slots_populated = False
        for row in crests.TEAM_CRESTS:
            panel.slot.addItem(row.label, row)
        panel._populate_slots()
        self.assertEqual(panel.slot.count(), len(crests.TEAM_CRESTS))


if __name__ == "__main__":
    unittest.main()
