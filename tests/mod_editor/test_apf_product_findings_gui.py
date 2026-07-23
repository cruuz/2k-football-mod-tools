from __future__ import annotations

import os
from types import SimpleNamespace
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication, QTabWidget  # noqa: E402

from mod_editor.apf_studio.gui import (  # noqa: E402
    InspectorCategoryPage,
    ScorebugStudioPage,
    _load_gameplay_inspector,
)
from mod_editor.apf_studio.models import (  # noqa: E402
    ApfCategory,
    ApfStatus,
    CapabilityCard,
)
from mod_editor.apf_studio.product_findings import (  # noqa: E402
    presentation_snapshot,
)


def _run_task_now(
    _title: str,
    operation: object,
    complete: object,
    _blocking: bool,
) -> None:
    result = operation(lambda *_progress: None)  # type: ignore[operator]
    complete(result)  # type: ignore[operator]


class _GameplayFacade:
    source_ready = True
    source = SimpleNamespace(source_sha256="d" * 64)

    @staticmethod
    def capability_cards(category: ApfCategory) -> tuple[CapabilityCard, ...]:
        if category is not ApfCategory.GAMEPLAY:
            return ()
        return (
            CapabilityCard(
                "apf2k8.catching_drops.behavior",
                "APF catching and drops",
                "Final outcome ownership remains unproved.",
                category,
                ApfStatus.COMING_SOON,
            ),
            CapabilityCard(
                "apf2k8.cpu_ai_draft.logic",
                "APF CPU AI and draft logic",
                "The retained weights are lineage evidence only.",
                category,
                ApfStatus.PREVIEW,
            ),
            CapabilityCard(
                "apf2k8.gameplay_tuning_sliders.roster_view",
                "APF gameplay sliders and roster viewer",
                "The 21 stock controls are mapped read-only.",
                category,
                ApfStatus.PREVIEW,
            ),
        )


class ApfProductFindingsGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def test_gameplay_page_replaces_the_empty_asset_browser_with_38_rows(self) -> None:
        page = InspectorCategoryPage(
            _GameplayFacade(),  # type: ignore[arg-type]
            ApfCategory.GAMEPLAY,
            _run_task_now,
            "Mapped sliders and retained draft lineage",
            _load_gameplay_inspector,
            include_assets=False,
            packaged_findings=True,
        )
        try:
            page.set_context(SimpleNamespace())  # type: ignore[arg-type]
            self.application.processEvents()
            self.assertIsNone(page.assets)
            self.assertIsNotNone(page.inspector.model)
            assert page.inspector.model is not None
            self.assertEqual(len(page.inspector.model.rows), 38)
            self.assertEqual(page.inspector.table.rowCount(), 38)
            self.assertEqual(page.inspector.count.text(), "38 decoded rows")
            self.assertTrue(page.inspector.export_rows_button.isEnabled())
            self.assertIn("Sliders: 21", page.inspector.summary.text())
            self.assertEqual(page.capabilities.layout.count(), 3)
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_scorebug_workspace_keeps_editor_raw_assets_and_semantic_map(self) -> None:
        page = ScorebugStudioPage(
            SimpleNamespace(
                source_ready=False,
                modified_asset_ids=frozenset(),
            ),  # type: ignore[arg-type]
            lambda *_args, **_kwargs: None,
        )
        try:
            workspace = page.findChild(QTabWidget, "workspaceTabs")
            self.assertIsNotNone(workspace)
            assert workspace is not None
            self.assertEqual(workspace.count(), 3)
            self.assertEqual(
                tuple(workspace.tabText(index) for index in range(3)),
                ("Presentation Map", "Digital Font", "Raw Presentation Assets"),
            )
            snapshot = presentation_snapshot()
            page.presentation.set_model(snapshot.model, "fixture")
            self.assertEqual(page.presentation.table.rowCount(), 8)
            self.assertEqual(page.presentation.count.text(), "8 decoded rows")
            self.assertIs(workspace.widget(1), page.digital_font)
            self.assertIs(workspace.widget(2), page.browser)
        finally:
            page.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
