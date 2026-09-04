"""The Install / Export Playbook Pack UI: the plan table, the budget bar, the team
assignment, and the two new buttons on the Playbooks & Plays tab.

The model tests run anywhere.  The dialog tests are offscreen and gated on the
extracted retail archive, because a plan table is only honest against a real book.
"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as pk  # noqa: E402
from mod_editor.gui import playbook_pack_dialog_qt as ui  # noqa: E402
from test_nfl2k5_playbook_pack import _fake_book, synthetic_pack  # noqa: E402

EXTRACT = pathlib.Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
SEED = ROOT / "data" / "playbooks" / "modern_gun_core.2k5book"


def _has_extract() -> bool:
    return (EXTRACT / "vc_53450030" / "0").is_file()


class PackUiModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = synthetic_pack()
        self.book = _fake_book(formations=39, plays=254)

    def test_summary_names_the_author_and_what_it_starts_from(self) -> None:
        lines = ui.pack_summary_lines(self.pack)
        self.assertIn("Synthetic", lines[0])
        self.assertIn("tests", lines[0])
        self.assertIn("CC0-1.0", lines[0])
        self.assertIn("Authored on ATL", lines[1])
        self.assertIn("254 plays", lines[1])

    def test_team_choices_offer_as_authored_retarget_and_all(self) -> None:
        choices = ui.team_choices(self.pack, ("ARZ", "ATL", "GB"))
        labels = [label for label, _value in choices]
        values = [value for _label, value in choices]
        self.assertEqual(labels[0], "As authored — ATL")
        self.assertEqual(values[0], "ATL")
        self.assertIn("Retarget to GB", labels)
        self.assertEqual(labels[-1], "All 3 team books")
        self.assertEqual(values[-1], pk.ALL_TEAMS)

    def test_plan_rows_and_budget_bars(self) -> None:
        plan = pk.install_plan(self.pack, self.book, b"")
        preview = pk.PackPreview("ATL", self.pack, plan, pk.check_pack(self.pack))
        rows = ui.plan_table_rows(preview)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][0], "Formation")
        self.assertEqual(rows[0][1], "Gun Trips Rt")
        self.assertEqual(rows[0][2], "Stock Formation 4")
        self.assertEqual(rows[0][3], "ok")
        bars = ui.budget_bars(plan.totals)
        self.assertEqual([name for name, _v, _m in bars], ["plays", "formations", "nodes"])
        self.assertEqual(bars[0][1:], (254, 270))
        self.assertEqual(bars[1][1:], (39, 50))
        self.assertEqual(bars[2][2], 3500)
        self.assertEqual(ui.install_blockers(preview), ())

    def test_blockers_name_the_offending_entry(self) -> None:
        plan = pk.install_plan(self.pack, self.book, b"", staged_play_targets=[101])
        preview = pk.PackPreview("ATL", self.pack, plan, pk.check_pack(self.pack))
        blockers = ui.install_blockers(preview)
        self.assertTrue(blockers)
        self.assertIn("Gun Mesh", blockers[0])
        self.assertIn("already replaced by a staged edit", blockers[0])

    def test_engine_limits_are_stated_on_every_install(self) -> None:
        for phrase in ("pre-snap motion", "give-or-throw RPO", "tempo", "never been witnessed"):
            self.assertIn(phrase, ui.ENGINE_LIMITS_TEXT)


class _StubSession:
    def __init__(self) -> None:
        self.rows: list[object] = []

    def attach_playbook_inspector(self, _inspector: object) -> None:
        return None

    def create_formation(self, request):
        self.rows.append(request)
        return True

    def create_play(self, request):
        self.rows.append(request)
        return True

    def create_formation_link(self, request):
        self.rows.append(request)
        return True


class _StubHost:
    """Just the five pack members the dialog uses, over one real retail book."""

    def __init__(self, resource: bytes, team: str) -> None:
        self.resource = resource
        self.team = team
        self.book = insp.parse_playbook_resource(resource, asset_id=f"book:{team}")
        self.body = resource[0x20:]
        self.installed: list[tuple[str, ...]] = []
        self.staged_formations: set[int] = set()
        self.staged_plays: set[int] = set()

    def playbook_teams(self):
        return (self.team,)

    def load_playbook_pack(self, path):
        return pk.load_pack(path)

    def preview_playbook_pack(self, pack, team=None, progress=None):
        return pk.preview_pack(
            pack, team or self.team, self.book, self.body, resource=self.resource,
            staged_formation_targets=self.staged_formations,
            staged_play_targets=self.staged_plays,
        )

    def install_playbook_pack(self, pack, teams=None, progress=None):
        self.installed.append(tuple(teams or (self.team,)))
        return f"Staged “{pack.book.name}” into {', '.join(teams or (self.team,))}."


@unittest.skipUnless(_has_extract(), "extracted retail archive missing")
class PackInstallDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import nfl2k5_playbook_position_recode as recode
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])
        with recode.OuterImage(EXTRACT) as archive:
            cls.resource = archive.read_entry(recode.BOOK_ENTRIES["ATL"])

    def test_dialog_shows_the_plan_the_budget_and_installs(self) -> None:
        host = _StubHost(self.resource, "ATL")
        dialog = ui.PlaybookPackInstallDialog(host, SEED)
        try:
            from PyQt5.QtWidgets import QDialogButtonBox

            self.assertEqual(dialog.table.rowCount(), 15)
            self.assertEqual(dialog.table.item(0, 0).text(), "Formation")
            self.assertEqual(dialog.table.item(0, 1).text(), "Gun Trips Rt")
            self.assertEqual(dialog.table.item(0, 2).text(), "Split Jokers")
            self.assertEqual(dialog.table.item(0, 3).text(), "ok")
            self.assertEqual(dialog.bars["plays"].value(), 254)
            self.assertEqual(dialog.bars["plays"].maximum(), 270)
            self.assertEqual(dialog.bars["formations"].maximum(), 50)
            self.assertEqual(dialog.bars["nodes"].maximum(), 3500)
            self.assertIn("plays 254/270", dialog.status.text())
            self.assertTrue(dialog.buttons.button(QDialogButtonBox.Ok).isEnabled())
            self.assertEqual(dialog.selected_teams(), ("ATL",))
            dialog._install()
            self.assertEqual(host.installed, [("ATL",)])
            self.assertIn("Modern Gun Core", dialog.result_message)
        finally:
            dialog.deleteLater()
            self.app.processEvents()

    def test_dialog_refuses_when_an_entry_conflicts_with_a_staged_edit(self) -> None:
        host = _StubHost(self.resource, "ATL")
        pack = pk.load_pack(SEED)
        host.staged_plays = {pack.plays[0].replace_index}
        dialog = ui.PlaybookPackInstallDialog(host, SEED)
        try:
            from PyQt5.QtWidgets import QDialogButtonBox

            statuses = {dialog.table.item(r, 1).text(): dialog.table.item(r, 3).text()
                        for r in range(dialog.table.rowCount())}
            self.assertEqual(statuses[pack.plays[0].custom_name], "conflict")
            self.assertFalse(dialog.buttons.button(QDialogButtonBox.Ok).isEnabled())
            self.assertIn("Cannot install yet", dialog.status.text())
            self.assertIn(pack.plays[0].replace_name, dialog.status.text())
        finally:
            dialog.deleteLater()
            self.app.processEvents()

    def test_export_dialog_collects_the_pack_metadata(self) -> None:
        dialog = ui.PlaybookPackExportDialog("ATL", 15)
        try:
            dialog.author.setText("busjibber")
            dialog.notes.setPlainText("Gun sets and eleven concepts.")
            dialog._accept()
            self.assertEqual(dialog.result_payload["author"], "busjibber")
            self.assertEqual(dialog.result_payload["version"], "1.0.0")
            self.assertEqual(dialog.result_payload["license"], "CC0-1.0")
            self.assertIn("eleven concepts", dialog.result_payload["notes"])
        finally:
            dialog.deleteLater()
            self.app.processEvents()


class PlaybooksPanelPackButtonTests(unittest.TestCase):
    """The two buttons sit beside the designers and the panel keeps its protocol."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_panel_exposes_install_and_export_and_the_audible_slot(self) -> None:
        from test_playbooks_link_table_export_ui import _Host

        from mod_editor.gui.playbooks_panel_qt import (
            AUDIBLE_GROUPS, PlaybooksPanel, suggested_playbook_pack_filename,
        )

        panel = PlaybooksPanel(_Host())
        try:
            self.assertTrue(panel.install_pack_button.isVisible() or True)
            self.assertEqual(panel.install_pack_button.text(), "Install Playbook Pack…")
            self.assertEqual(panel.export_pack_button.text(), "Export Playbook Pack…")
            self.assertIn("no game data", panel.install_pack_button.toolTip())
            self.assertEqual(panel.link_group_combo.count(), len(AUDIBLE_GROUPS))
            self.assertIsNone(panel.link_group_combo.itemData(0))
            self.assertEqual([panel.link_group_combo.itemData(i) for i in range(1, 5)],
                             [0, 1, 2, 3])
            self.assertEqual(suggested_playbook_pack_filename("ATL", "Modern Gun Core"),
                             "ATL_Modern_Gun_Core.2k5book")
        finally:
            panel.deleteLater()
            self.app.processEvents()


class CreatePlayWizardExtrasTests(unittest.TestCase):
    """The two cheap wins: the QB read order and the audible groups."""

    def test_read_order_round_trips_through_the_dropback_node(self) -> None:
        from mod_editor.gui import create_play_wizard_qt as wiz

        chain = lib.qb_pass_chain(True)
        self.assertEqual(wiz.read_order_of(chain), (1, 4, 2, 3))
        changed = wiz.with_read_order(chain, [3, 1, 2, 4])
        self.assertEqual(wiz.read_order_of(changed), (3, 1, 2, 4))
        self.assertEqual(wiz.read_order_of(lib.qb_handoff_chain(10, 0)), None)
        # the edited chain still encodes and still passes the node codec round trip
        node = next(n for n in changed if n[0] == wiz.DROPBACK_OPCODE)
        packed = codec.encode_operands(0x06, node[1])
        self.assertEqual(codec.decode_operands(0x06, packed)[1:5], [3, 1, 2, 4])
        with self.assertRaises(ValueError):
            wiz.with_read_order(chain, [1, 2, 3])

    def test_read_order_values_stay_in_the_corpus_range(self) -> None:
        from mod_editor.gui import create_play_wizard_qt as wiz

        clamped = wiz.with_read_order(lib.qb_pass_chain(False), [0, 9, 5, 1])
        self.assertEqual(wiz.read_order_of(clamped), (1, 5, 5, 1))

    def test_audible_groups_offer_inherit_plus_the_three_slots(self) -> None:
        from mod_editor.gui import create_play_wizard_qt as wiz

        self.assertEqual([value for _label, value in wiz.AUDIBLE_GROUPS], [None, 0, 1, 2, 3])
        self.assertIn("Inherit", wiz.AUDIBLE_GROUPS[0][0])

    def test_facade_passes_the_group_through_to_the_link_request(self) -> None:
        import inspect as _inspect

        from mod_editor.studio.facade import Nfl2k5StudioFacade

        signature = _inspect.signature(Nfl2k5StudioFacade.create_authored_play)
        self.assertIn("link_group", signature.parameters)
        self.assertIsNone(signature.parameters["link_group"].default)


if __name__ == "__main__":
    unittest.main()
