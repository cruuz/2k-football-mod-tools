from __future__ import annotations

import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

from mod_editor.apf_studio.inspectors import InspectorRow, PagedModel  # noqa: E402
from mod_editor.apf_studio.playbook_route_qt import (  # noqa: E402
    PlayAssignmentRoutePanel,
)
from mod_editor.core.apf2k8_playbook_route_writer import (  # noqa: E402
    ROUTE_ORPHAN_MESSAGE,
)


class _Facade:
    source_ready = True

    def __init__(self) -> None:
        self.session = SimpleNamespace(modifications=())
        self.calls: list[tuple[object, ...]] = []

    def replace_play_assignment_route(self, *values, progress):
        progress("copy", 1, 1)
        self.calls.append(("copy", *values))
        return object()

    def swap_play_assignment_routes(self, *values, progress):
        progress("swap", 2, 2)
        self.calls.append(("swap", *values))
        return object()

    def revert(self, asset_id, progress):
        progress("revert", 1, 1)
        self.calls.append(("revert", asset_id))
        return True


class _OrphanFacade(_Facade):
    """Copy always orphans; the relayed pair is the only way through."""

    def __init__(self, candidates: tuple[tuple[int, int], ...]) -> None:
        super().__init__()
        self.candidates = candidates
        self.candidate_calls: list[tuple[object, ...]] = []

    def replace_play_assignment_route(self, *values, progress):
        progress("copy", 1, 1)
        self.calls.append(("copy", *values))
        raise ValueError(ROUTE_ORPHAN_MESSAGE)

    def relay_play_assignment_route_candidates(self, *values):
        self.candidate_calls.append(tuple(values))
        return self.candidates

    def copy_play_assignment_route_via_relay(self, *values, progress):
        progress("relay", 2, 2)
        self.calls.append(("relay-copy", *values))
        target_play, target_slot, donor_play, donor_slot, relay_play, relay_slot = values

        def modification(
            play_index: int, slot_index: int, donor_p: int, donor_s: int
        ) -> SimpleNamespace:
            asset_id = f"play-route:apf:playbook:180:0:p{play_index}:s{slot_index}"
            return SimpleNamespace(
                asset_id=asset_id,
                kind="play_assignment_route",
                metadata={
                    "asset_id": asset_id,
                    "target_play_index": play_index,
                    "target_slot_index": slot_index,
                    "donor_play_index": donor_p,
                    "donor_slot_index": donor_s,
                },
            )

        self.session.modifications = (
            modification(target_play, target_slot, donor_play, donor_slot),
            modification(relay_play, relay_slot, target_play, target_slot),
        )
        return self.session.modifications


def _run_task(_label, operation, complete, _blocking, show_errors=True, on_error=None):
    try:
        result = operation(lambda _stage, _done, _total: None)
    except Exception as exc:
        if on_error is None:
            raise
        on_error(str(exc))
        return False
    complete(result)
    return True


def _model() -> PagedModel:
    rows = tuple(
        InspectorRow(
            row_id=f"apf:playbook:180:play:{index}",
            kind="play",
            title=name,
            subtitle="MASTER",
            fields={"index": index, "name": name},
            _search_text=name.casefold(),
        )
        for index, name in ((0, "Strong Power"), (1, "Weak Toss"))
    )
    return PagedModel(rows, ())


class PlayAssignmentRoutePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_play_and_slot_pickers_call_exact_copy_and_swap_routes(self) -> None:
        facade = _Facade()
        panel = PlayAssignmentRoutePanel(facade, _run_task)
        panel.set_model(_model())
        self.assertEqual(panel.target_play.count(), 2)
        self.assertEqual(panel.target_slot.count(), 11)
        panel.target_play.setCurrentIndex(0)
        panel.target_slot.setCurrentIndex(2)
        panel.donor_play.setCurrentIndex(1)
        panel.donor_slot.setCurrentIndex(3)
        panel._copy()
        panel._swap()
        self.assertEqual(
            facade.calls,
            [("copy", 0, 2, 1, 3), ("swap", 0, 2, 1, 3)],
        )

    def test_staged_table_cells_use_readable_colors(self) -> None:
        facade = _Facade()
        facade.session.modifications = (
            SimpleNamespace(
                asset_id="play-route:apf:playbook:180:0:p0:s0",
                kind="play_assignment_route",
                metadata={
                    "asset_id": "play-route:apf:playbook:180:0:p0:s0",
                    "target_play_index": 0,
                    "target_slot_index": 2,
                    "donor_play_index": 1,
                    "donor_slot_index": 3,
                },
            ),
        )
        panel = PlayAssignmentRoutePanel(facade, _run_task)
        panel.set_model(_model())
        panel.refresh()
        self.assertEqual(panel.table.rowCount(), 1)
        for column in range(3):
            item = panel.table.item(0, column)
            self.assertIsNotNone(item)
            self.assertEqual(item.foreground().color().name(), "#dce8f5")
            self.assertEqual(item.background().color().name(), "#0c1421")

    def test_no_game_disables_mutation(self) -> None:
        facade = _Facade()
        facade.source_ready = False
        panel = PlayAssignmentRoutePanel(facade, _run_task)
        panel.set_model(_model())
        # Never silent-gray: clickable + disableReason teaches Load.
        self.assertTrue(panel.copy_button.isEnabled())
        self.assertTrue(panel.swap_button.isEnabled())
        self.assertIn(
            "Load",
            str(panel.copy_button.property("disableReason") or ""),
        )
        self.assertIn(
            "Load",
            str(panel.swap_button.property("disableReason") or ""),
        )


class PlayAssignmentRoutePanelRelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self, facade) -> PlayAssignmentRoutePanel:
        panel = PlayAssignmentRoutePanel(facade, _run_task)
        panel.set_model(_model())
        panel.target_play.setCurrentIndex(0)
        panel.target_slot.setCurrentIndex(2)
        panel.donor_play.setCurrentIndex(1)
        panel.donor_slot.setCurrentIndex(3)
        return panel

    def _click_button(self, prefix: str):
        shown: list[QMessageBox] = []

        def exec_(box: QMessageBox) -> int:
            shown.append(box)
            for button in box.buttons():
                if button.text().startswith(prefix):
                    button.click()
                    return 0
            raise AssertionError(f"No button starting with {prefix!r}")

        return shown, exec_

    def test_orphan_copy_offers_relay_and_invokes_relayed_copy(self) -> None:
        facade = _OrphanFacade(candidates=((1, 2),))
        panel = self._panel(facade)
        shown, exec_ = self._click_button("Copy via relay")
        with patch.object(QMessageBox, "exec_", exec_):
            panel._copy()
        self.assertEqual(len(shown), 1)
        self.assertEqual(shown[0].text(), ROUTE_ORPHAN_MESSAGE)
        self.assertIn(
            "Copy via relay play Weak Toss (slot 3)",
            [button.text() for button in shown[0].buttons()],
        )
        self.assertEqual(facade.candidate_calls, [(0, 2, 1, 3)])
        self.assertEqual(
            facade.calls,
            [("copy", 0, 2, 1, 3), ("relay-copy", 0, 2, 1, 3, 1, 2)],
        )
        # The panel refreshed its staged rows from the relayed pair.
        self.assertEqual(panel.table.rowCount(), 2)
        self.assertEqual(
            panel.table.item(0, 0).text(), "Strong Power · slot 3"
        )
        self.assertEqual(
            panel.table.item(1, 0).text(), "Weak Toss · slot 3"
        )

    def test_orphan_copy_pick_relay_uses_input_dialog(self) -> None:
        facade = _OrphanFacade(candidates=((0, 4), (1, 2)))
        panel = self._panel(facade)
        shown, exec_ = self._click_button("Pick relay")
        labels: list[str] = []

        def get_item(_parent, _title, _label, items, _current, _editable, **_kwargs):
            labels.extend(items)
            return "Weak Toss · slot 3", True

        with patch.object(QMessageBox, "exec_", exec_), patch.object(
            QInputDialog, "getItem", side_effect=get_item
        ):
            panel._copy()
        self.assertEqual(
            labels, ["Strong Power · slot 5", "Weak Toss · slot 3"]
        )
        self.assertEqual(
            facade.calls,
            [("copy", 0, 2, 1, 3), ("relay-copy", 0, 2, 1, 3, 1, 2)],
        )

    def test_orphan_copy_cancel_stages_nothing(self) -> None:
        facade = _OrphanFacade(candidates=((1, 2),))
        panel = self._panel(facade)
        with patch.object(QMessageBox, "exec_", return_value=0):
            panel._copy()
        self.assertEqual(facade.calls, [("copy", 0, 2, 1, 3)])

    def test_orphan_copy_without_candidates_warns(self) -> None:
        facade = _OrphanFacade(candidates=())
        panel = self._panel(facade)
        with patch.object(QMessageBox, "warning") as warning:
            panel._copy()
        self.assertEqual(len(warning.mock_calls), 1)
        self.assertEqual(facade.calls, [("copy", 0, 2, 1, 3)])
        self.assertEqual(facade.candidate_calls, [(0, 2, 1, 3)])


if __name__ == "__main__":
    unittest.main()
