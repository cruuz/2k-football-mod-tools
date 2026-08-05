"""Ending uniform sharing: the change that makes per-team helmet edits possible.

APF's forty teams draw helmets from only six textures. That is why a modder who
paints a wing for one team finds it on several others, and why the advice in
that community has been "this is best we can do with these teams". The game
ships twenty-four helmet packages and references six; eighteen sit unused.

The plan that fixes it already existed as a command-line writer and was never
offered in the app. These tests cover the seam that offers it, and they are
deliberately about *honesty* as much as function: the numbers shown to a user
have to be the numbers in the frozen plan, the plan must be the one the writer
will actually accept, and the described change must not overstate what is
proved.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.apf_studio import uniform_independence as independence  # noqa: E402


@unittest.skipUnless(
    independence.plan_available(), "pinned allocation reports not present"
)
class PlanDescriptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = independence.describe_plan()

    def test_it_describes_all_eleven_families(self) -> None:
        self.assertEqual(len(self.plan.families), 11)
        names = {row.family for row in self.plan.families}
        self.assertIn("helmet", names)
        self.assertIn("jersey", names)
        self.assertIn("sock", names)

    def test_helmets_are_the_headline_and_come_first(self) -> None:
        """The reported wall is helmets, so they lead."""

        self.assertEqual(self.plan.families[0].family, "helmet")
        self.assertIn("helmet", self.plan.headline())

    def test_the_helmet_numbers_match_the_shipped_game(self) -> None:
        """Six shared textures become twenty-four, one per built-in team."""

        helmet = self.plan.helmet
        self.assertIsNotNone(helmet)
        self.assertEqual(helmet.distinct_before, 6)
        self.assertEqual(helmet.distinct_after, 24)
        self.assertEqual(helmet.teams_changed, 18)
        self.assertEqual(helmet.catalog_count, 24)
        self.assertEqual(helmet.selector_slot, 3)

    def test_every_family_ends_with_no_more_sharing_than_it_started(self) -> None:
        for row in self.plan.families:
            with self.subTest(family=row.family):
                self.assertGreaterEqual(row.distinct_after, row.distinct_before)
                self.assertLessEqual(row.distinct_after, row.catalog_count)

    def test_families_that_already_differ_are_reported_as_unchanged(self) -> None:
        """Not everything is shared; claiming otherwise would be a lie."""

        by_name = {row.family: row for row in self.plan.families}
        for name in ("logo", "textlogo", "glove", "shoe"):
            with self.subTest(family=name):
                self.assertTrue(by_name[name].already_independent)
                self.assertIn("already", by_name[name].summary)

    def test_the_summaries_are_plain_language(self) -> None:
        helmet = self.plan.helmet
        self.assertIn("6 shared textures become 24", helmet.summary)
        self.assertIn("18 teams stop sharing", helmet.summary)

    def test_the_total_matches_the_sum_of_the_families(self) -> None:
        self.assertEqual(
            self.plan.total_teams_changed,
            sum(row.teams_changed for row in self.plan.families),
        )


@unittest.skipUnless(
    independence.plan_available(), "pinned allocation reports not present"
)
class PlanMatchesTheWriterTests(unittest.TestCase):
    """What is shown must be what the writer will accept, or the UI lies."""

    def test_the_described_plan_is_the_one_the_writer_admits(self) -> None:
        import apf_uniform_selector_patch as writer

        allocation, _raw, _capacity, _capacity_raw = writer.load_authorities()
        recipe = writer.expected_recipe(allocation)
        described = {row.family: row for row in independence.describe_plan().families}

        self.assertEqual(len(recipe["families"]), len(described))
        for family in recipe["families"]:
            row = described[family["family"]]
            assignments = family["assignments"]
            with self.subTest(family=row.family):
                self.assertEqual(row.catalog_count, family["catalog_count"])
                self.assertEqual(row.selector_slot, family["selector_slot"])
                self.assertEqual(
                    row.distinct_before,
                    len({a["expected_retail_asset_index"] for a in assignments}),
                )
                self.assertEqual(
                    row.distinct_after,
                    len({a["replacement_asset_index"] for a in assignments}),
                )

    def test_the_writer_still_refuses_anything_but_that_plan(self) -> None:
        """The seam adds no write authority; the frozen gate must stay shut."""

        import json

        import apf_uniform_selector_patch as writer

        allocation, _raw, _capacity, _capacity_raw = writer.load_authorities()
        recipe = writer.expected_recipe(allocation)
        for family in recipe["families"]:
            if family["family"] == "helmet":
                family["assignments"][0]["replacement_asset_index"] = 23
                break

        with tempfile.TemporaryDirectory(prefix="apf-independence-") as work:
            path = Path(work) / "tampered.json"
            path.write_bytes(writer.transport.canonical_json_bytes(recipe))
            with self.assertRaises(writer.PatchError) as caught:
                writer.load_recipe(path)
        self.assertIn("frozen", str(caught.exception))


@unittest.skipUnless(
    independence.plan_available(), "pinned allocation reports not present"
)
class SharingLookupTests(unittest.TestCase):
    """The question that was never askable in the app: who else uses this?"""

    def test_the_helmet_the_americans_wear_is_shared_by_many_teams(self) -> None:
        """This is the reported bug, stated as data.

        Helmet 1 carries the Americans -- the team modders rebuild as the
        Eagles -- along with fifteen others. Painting a wing there puts it on
        all of them, which is exactly what people ran into.
        """

        shared = independence.teams_using("helmet", 1)
        self.assertTrue(shared.is_shared)
        self.assertIn("Americans", shared.teams)
        self.assertEqual(len(shared.teams), 16)
        self.assertIn("Shared by 16 teams", shared.warning())

    def test_an_unused_helmet_is_reported_as_free(self) -> None:
        """Eighteen helmets belong to nobody; that is the room to move."""

        shared = independence.teams_using("helmet", 5)
        self.assertEqual(shared.teams, ())
        self.assertFalse(shared.is_shared)
        self.assertIn("No built-in team uses this", shared.warning())

    def test_a_single_owner_is_reported_as_safe(self) -> None:
        shared = independence.teams_using("helmet", 16)
        self.assertEqual(len(shared.teams), 1)
        self.assertFalse(shared.is_shared)
        self.assertIn("affects that team alone", shared.warning())

    def test_every_helmet_resolves_and_the_totals_add_up(self) -> None:
        """Twenty-four teams, each accounted for exactly once."""

        total = 0
        for index in range(24):
            shared = independence.teams_using("helmet", index)
            total += len(shared.teams)
        self.assertEqual(total, 24)

    def test_an_unknown_family_is_refused_by_name(self) -> None:
        with self.assertRaises(independence.UniformIndependenceError):
            independence.teams_using("cape", 0)


class ApplyGuardTests(unittest.TestCase):
    """Refusals happen before anything is written."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="apf-independence-apply-"))

    def test_a_missing_game_volume_is_refused_by_name(self) -> None:
        with self.assertRaises(independence.UniformIndependenceError) as caught:
            independence.apply_plan(
                self.root / "absent",
                self.root / "0A",
                self.root / "manifest.json",
            )
        self.assertIn("not found", str(caught.exception))

    def test_it_refuses_to_overwrite_an_existing_output(self) -> None:
        source = self.root / "0A-source"
        source.write_bytes(b"not a real volume")
        existing = self.root / "0A"
        existing.write_bytes(b"do not clobber me")
        with self.assertRaises(independence.UniformIndependenceError):
            independence.apply_plan(source, existing, self.root / "manifest.json")
        self.assertEqual(existing.read_bytes(), b"do not clobber me")

    def test_it_refuses_to_overwrite_an_existing_manifest(self) -> None:
        source = self.root / "0A-source"
        source.write_bytes(b"not a real volume")
        manifest = self.root / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        with self.assertRaises(independence.UniformIndependenceError):
            independence.apply_plan(source, self.root / "0A", manifest)


@unittest.skipUnless(
    independence.plan_available(), "pinned allocation reports not present"
)
class PanelTests(unittest.TestCase):
    """The panel has to survive having no game loaded, which is how it opens."""

    @classmethod
    def setUpClass(cls) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _panel(self, ready: bool):
        from mod_editor.apf_studio.uniform_independence_panel import (
            UniformIndependencePanel,
        )

        class _Source:
            index_0a = Path("/nonexistent/0A")

        class _Facade:
            source_ready = ready
            source = _Source() if ready else None

            def __getattr__(self, name):
                return None

        return UniformIndependencePanel(_Facade(), lambda *a: None)

    def test_it_lists_only_the_families_that_change(self) -> None:
        panel = self._panel(ready=True)
        self.assertEqual(panel.table.rowCount(), 7)
        first = panel.table.item(0, 0).text()
        self.assertEqual(first, "helmet")

    def test_the_helmet_row_carries_the_real_numbers(self) -> None:
        panel = self._panel(ready=True)
        row = [panel.table.item(0, column).text() for column in range(4)]
        self.assertEqual(row, ["helmet", "6", "24", "18"])

    def test_it_opens_without_a_game_and_disables_the_action(self) -> None:
        panel = self._panel(ready=False)
        self.assertFalse(panel.apply_button.isEnabled())
        self.assertTrue(panel.headline.text())

    def test_the_caveat_states_what_is_not_proved(self) -> None:
        """A modder should not spend an hour on this believing more than is known."""

        panel = self._panel(ready=True)
        text = panel.caveat.text()
        self.assertIn("never changes the one you loaded", text)
        self.assertIn("Xbox 360", text)

    def test_source_ready_toggles_the_action(self) -> None:
        panel = self._panel(ready=True)
        panel.set_source_ready(False)
        self.assertFalse(panel.apply_button.isEnabled())
        panel.set_source_ready(True)
        self.assertTrue(panel.apply_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
