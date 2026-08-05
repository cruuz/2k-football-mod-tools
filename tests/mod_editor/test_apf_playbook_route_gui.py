from __future__ import annotations

import os
from types import SimpleNamespace
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.inspectors import InspectorRow, PagedModel  # noqa: E402
from mod_editor.apf_studio.playbook_route_qt import (  # noqa: E402
    PlayAssignmentRoutePanel,
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


def _run_task(_label, operation, complete, _blocking):
    result = operation(lambda _stage, _done, _total: None)
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

    def test_no_game_disables_mutation(self) -> None:
        facade = _Facade()
        facade.source_ready = False
        panel = PlayAssignmentRoutePanel(facade, _run_task)
        panel.set_model(_model())
        self.assertFalse(panel.copy_button.isEnabled())
        self.assertFalse(panel.swap_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
