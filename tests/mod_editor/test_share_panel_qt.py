"""Share tab: gating, background export / check / apply on synthetic images, studio wiring."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tests" / "mod_editor"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import modpack  # noqa: E402
from mod_editor.gui.share_panel_qt import SharePanel  # noqa: E402
from test_modpack import make_pair  # noqa: E402


def wait_for(panel: SharePanel, app: QApplication, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while panel.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert not panel.busy, "background task did not finish"


class SharePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="share-panel-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.base, self.patched, self.base_bytes, self.patched_bytes = make_pair(self.tmp)
        self.panel = SharePanel()
        self.panel._confirm = lambda title, text: True          # no modal dialogs offscreen
        self.notices: list[tuple[str, str]] = []
        self.panel._notify = lambda kind, title, text: self.notices.append((kind, title))
        self.addCleanup(self._teardown_panel)

    def _teardown_panel(self) -> None:
        self.panel.deleteLater()
        self.app.processEvents()

    def test_buttons_are_gated_on_the_fields(self) -> None:
        panel = self.panel
        self.assertFalse(panel.export_button.isEnabled())
        panel.base_field.setText(str(self.base))
        panel.patched_field.setText(str(self.patched))
        panel.out_field.setText(str(self.tmp / "x.2k5patch"))
        self.assertFalse(panel.export_button.isEnabled())       # name still empty
        panel.name_field.setText("Edits")
        self.assertTrue(panel.export_button.isEnabled())
        self.assertFalse(panel.check_button.isEnabled())
        self.assertFalse(panel.apply_button.isEnabled())
        panel.load_pack(self.tmp / "does-not-exist.2k5patch")
        self.assertIn("Not usable", panel.pack_summary.text())
        self.assertFalse(panel.check_button.isEnabled())

    def test_export_check_and_apply_run_in_the_background_and_round_trip(self) -> None:
        panel = self.panel
        pack_path = self.tmp / "panel.2k5patch"
        (self.tmp / "atlas.png").write_bytes(b"\x89PNG" + bytes(range(64)))
        panel.base_field.setText(str(self.base))
        panel.patched_field.setText(str(self.patched))
        panel.out_field.setText(str(pack_path))
        panel.name_field.setText("Panel edits")
        panel.author_field.setText("tests")
        panel.set_assets([self.tmp / "atlas.png"])
        panel.start_export()
        self.assertTrue(panel.busy)
        self.assertFalse(panel.export_button.isEnabled())
        wait_for(panel, self.app)
        self.assertTrue(pack_path.exists())
        self.assertIn("Wrote panel.2k5patch", panel.export_status.text())
        self.assertIn("6 run(s)", panel.export_status.text())
        self.assertEqual(panel.last_export["assets"][0]["path"], "assets/texture/atlas.png")
        self.assertEqual(self.notices[-1][0], "info")

        panel.load_pack(pack_path)
        summary = panel.pack_summary.text()
        self.assertIn("Panel edits", summary)
        self.assertIn("6 run(s)", summary)
        self.assertIn("Assets (1", summary)
        self.assertIn("NOT the retail disc image", summary)
        self.assertFalse(panel.apply_button.isEnabled())

        panel.source_field.setText(str(self.base))
        self.assertTrue(panel.check_button.isEnabled())
        panel.start_check()
        wait_for(panel, self.app)
        self.assertTrue(panel.check_status.text().startswith("READY"))
        self.assertFalse(panel.apply_button.isEnabled())         # no target yet
        out = self.tmp / "panel-out.xiso.iso"
        panel.target_field.setText(str(out))
        self.assertTrue(panel.apply_button.isEnabled())
        panel.start_apply()
        wait_for(panel, self.app)
        self.assertEqual(out.read_bytes(), self.patched_bytes)
        self.assertEqual(self.base.read_bytes(), self.base_bytes)
        self.assertIn("byte-identical", panel.apply_status.text())
        self.assertFalse(panel.apply_button.isEnabled())         # the check is spent

    def test_a_wrong_base_is_reported_and_apply_stays_disabled(self) -> None:
        panel = self.panel
        pack_path = self.tmp / "panel.2k5patch"
        modpack.export(self.base, self.patched, pack_path, {"name": "Edits"}, block=65536)
        wrong = bytearray(self.base_bytes)
        wrong[5001] ^= 1
        wrong_path = self.tmp / "wrong.xiso.iso"
        wrong_path.write_bytes(wrong)
        panel.load_pack(pack_path)
        panel.source_field.setText(str(wrong_path))
        panel.target_field.setText(str(self.tmp / "never.xiso.iso"))
        panel.start_check()
        wait_for(panel, self.app)
        self.assertTrue(panel.check_status.text().startswith("MISMATCH"))
        self.assertFalse(panel.apply_button.isEnabled())
        panel.start_apply()                                        # a no-op while not ready
        self.assertFalse(panel.busy)
        self.assertFalse((self.tmp / "never.xiso.iso").exists())
        panel.apply_check_report(modpack.check(pack_path, self.patched))
        self.assertTrue(panel.check_status.text().startswith("APPLIED"))
        self.assertFalse(panel.apply_button.isEnabled())

    def test_studio_offers_the_tab(self) -> None:
        from mod_editor.gui.studio_qt import StudioMainWindow

        window = StudioMainWindow()
        try:
            panels = window.findChildren(SharePanel)
            self.assertEqual(len(panels), 1)
            tabs = panels[0].parent()
            while tabs is not None and not hasattr(tabs, "tabText"):
                tabs = tabs.parent()
            self.assertIsNotNone(tabs)
            labels = [tabs.tabText(index).replace("&&", "&") for index in range(tabs.count())]
            # Share lives on the ★ Build & Share row next to Build, after the rework.
            self.assertEqual(labels, ["Build", "Share"])
        finally:
            window.deleteLater()
            self.app.processEvents()



class QuickShareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_build_receipt_prefills_the_export_and_arms_the_one_click_button(self) -> None:
        panel = SharePanel()
        self.assertFalse(panel.quick_export_button.isEnabled())
        base = Path(tempfile.gettempdir()) / "base.xiso.iso"
        target = Path(tempfile.gettempdir()) / "copy (advanced).xiso.iso"
        panel.prefill_from_build({"source": str(base), "target": str(target),
                                  "plan": {"name": "SOFTDRINK patch: advanced (everything modern)"}})
        self.assertEqual(Path(panel.base_field.text()), base)
        self.assertEqual(Path(panel.patched_field.text()), target)
        self.assertEqual(Path(panel.out_field.text()), target.with_name("copy (advanced).2k5patch"))
        self.assertEqual(panel.name_field.text(), "SOFTDRINK patch: advanced (everything modern)")
        self.assertEqual(panel.version_field.text(), "1")
        self.assertTrue(panel.quick_export_button.isEnabled())
        panel.prefill_from_build({"source": "", "target": ""})   # an empty receipt changes nothing
        self.assertEqual(Path(panel.base_field.text()), base)
        panel.deleteLater()
        self.app.processEvents()

if __name__ == "__main__":
    unittest.main()
